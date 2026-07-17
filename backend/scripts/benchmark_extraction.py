"""Benchmark candidate extraction models against the stored qwen3.6 labels.

Reruns the production extraction prompt (app.extract) with each candidate
model on a stratified sample of already-extracted emails — read-only against
inbox.db — then reports priority agreement, task/event presence agreement,
reliability, and speed. The stored qwen3.6 outputs are the reference; they
are a noisy reference, not ground truth, so every mismatch is also dumped to
a disagreement report for manual review.

Run from backend/:

    .venv/bin/python -m scripts.benchmark_extraction
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
import sqlite3
import statistics
import time
from collections import Counter
from pathlib import Path

import httpx

from app.db import connect
from app.extract import EXTRACTION_SCHEMA, SYSTEM_PROMPT, build_user_msg
from app.llm.ollama import OllamaClient

CANDIDATES = ["qwen3:4b", "qwen3:8b", "gemma3:12b-it-qat"]
BASELINE = "qwen3.6:latest"
CLASSES = ("high", "medium", "low")
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "benchmark"


class TimedOllamaClient(OllamaClient):
    """OllamaClient variant whose extraction call also returns eval metadata."""

    async def chat_json_meta(self, messages: list[dict]) -> tuple[dict, dict]:
        """Run the schema-bound extraction call, returning (result, metadata)."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": EXTRACTION_SCHEMA,
            "options": {"temperature": 0},
        }
        if await self._supports_thinking():
            payload["think"] = False
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=10)) as client:
            r = await client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
            if err := data.get("error"):
                raise RuntimeError(f"ollama: {err}")
            return json.loads(data["message"]["content"]), data

    async def unload(self) -> None:
        """Ask Ollama to evict this model from VRAM immediately."""
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": [], "keep_alive": 0},
            )


def parse_args() -> argparse.Namespace:
    """CLI options: candidate models, low-priority fill, seed, baseline size."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=CANDIDATES)
    parser.add_argument("--low-fill", type=int, default=60)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--baseline-n", type=int, default=20)
    return parser.parse_args()


def load_sample(
    conn: sqlite3.Connection, low_fill: int, seed: int
) -> list[sqlite3.Row]:
    """All high/medium and task/event emails, plus a seeded sample of low ones."""
    rows = conn.execute(
        "SELECT * FROM emails WHERE extracted = 1 ORDER BY id"
    ).fetchall()
    flagged = {
        r[0]
        for r in conn.execute(
            "SELECT email_id FROM tasks UNION SELECT email_id FROM events"
        )
    }
    keep = [
        r for r in rows if r["priority"] in ("high", "medium") or r["id"] in flagged
    ]
    kept_ids = {r["id"] for r in keep}
    low_pool = [r for r in rows if r["id"] not in kept_ids]
    keep += random.Random(seed).sample(low_pool, min(low_fill, len(low_pool)))
    keep.sort(key=lambda r: r["id"])
    return keep


def load_reference(conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
    """Stored qwen3.6 output for one email: priority, task texts, event titles."""
    tasks = [
        r[0]
        for r in conn.execute("SELECT text FROM tasks WHERE email_id = ?", (row["id"],))
    ]
    events = [
        r[0]
        for r in conn.execute(
            "SELECT title FROM events WHERE email_id = ?", (row["id"],)
        )
    ]
    return {"priority": row["priority"], "tasks": tasks, "events": events}


def _messages(row: sqlite3.Row) -> list[dict]:
    """The exact chat messages the production extraction pass would send."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_msg(row)},
    ]


async def run_model(model: str, sample: list[sqlite3.Row]) -> list[dict]:
    """Run the extraction prompt on each sampled email with one model."""
    client = TimedOllamaClient(model)
    await client.chat_json_meta(_messages(sample[0]))  # untimed warm-up / load
    results = []
    for i, row in enumerate(sample, 1):
        t0 = time.perf_counter()
        try:
            result, meta = await client.chat_json_meta(_messages(row))
            results.append(
                {
                    "email_id": row["id"],
                    "result": result,
                    "wall_s": time.perf_counter() - t0,
                    "eval_count": meta.get("eval_count", 0),
                    "eval_duration": meta.get("eval_duration", 0),
                }
            )
        except (httpx.HTTPError, RuntimeError, json.JSONDecodeError) as exc:
            results.append({"email_id": row["id"], "error": str(exc)})
        if i % 20 == 0 or i == len(sample):
            print(f"  {model}: {i}/{len(sample)}", flush=True)
    await client.unload()
    return results


def _entry(row: sqlite3.Row, ref: dict, out: dict, pred: str) -> dict:
    """One disagreement-report entry comparing reference and model output."""
    return {
        "email_id": row["id"],
        "subject": row["subject"],
        "sender": row["sender"],
        "date": row["date_utc"],
        "ref_priority": ref["priority"],
        "pred_priority": pred,
        "ref_tasks": ref["tasks"],
        "pred_tasks": [t.get("text", "") for t in out.get("tasks", [])],
        "ref_events": ref["events"],
        "pred_events": [e.get("title", "") for e in out.get("events", [])],
    }


def _metrics(
    model: str,
    confusion: Counter,
    failures: int,
    task_agree: int,
    event_agree: int,
    walls: list[float],
    toks: list[float],
) -> dict:
    """Aggregate one model's comparison counters into a summary row."""
    n = sum(confusion.values())
    ref_n = {c: sum(v for (r, _), v in confusion.items() if r == c) for c in CLASSES}
    recalls = {
        c: (confusion[(c, c)] / ref_n[c] if ref_n[c] else float("nan")) for c in CLASSES
    }
    return {
        "model": model,
        "scored": n,
        "failures": failures,
        "priority_agree": round(sum(confusion[(c, c)] for c in CLASSES) / n, 3),
        "high_recall": round(recalls["high"], 3),
        "medium_recall": round(recalls["medium"], 3),
        "low_recall": round(recalls["low"], 3),
        "high_as_low": confusion[("high", "low")],
        "task_presence_agree": round(task_agree / n, 3),
        "event_presence_agree": round(event_agree / n, 3),
        "mean_s": round(statistics.mean(walls), 2),
        "median_s": round(statistics.median(walls), 2),
        "tok_per_s": round(statistics.mean(toks), 1) if toks else 0.0,
    }


def score_model(
    model: str, sample: list[sqlite3.Row], refs: dict, results: list[dict]
) -> tuple[dict, list[dict]]:
    """Compare one model's outputs with the reference: (metrics, disagreements)."""
    by_id = {r["email_id"]: r for r in results}
    confusion: Counter = Counter()
    walls: list[float] = []
    toks: list[float] = []
    disagreements: list[dict] = []
    failures = task_agree = event_agree = 0
    for row in sample:
        res = by_id[row["id"]]
        if "error" in res:
            failures += 1
            continue
        out, ref = res["result"], refs[row["id"]]
        pred = out.get("priority")
        if pred not in CLASSES:
            pred = "invalid"
        confusion[(ref["priority"], pred)] += 1
        tasks_ok = bool(ref["tasks"]) == bool(out.get("tasks"))
        events_ok = bool(ref["events"]) == bool(out.get("events"))
        task_agree += tasks_ok
        event_agree += events_ok
        walls.append(res["wall_s"])
        if res["eval_duration"]:
            toks.append(res["eval_count"] / res["eval_duration"] * 1e9)
        if pred != ref["priority"] or not tasks_ok or not events_ok:
            disagreements.append(_entry(row, ref, out, pred))
    metrics = _metrics(model, confusion, failures, task_agree, event_agree, walls, toks)
    return metrics, disagreements


def write_summary(all_metrics: list[dict]) -> Path:
    """Write summary.csv and print the same table to stdout."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "summary.csv"
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(all_metrics[0].keys()))
        writer.writeheader()
        writer.writerows(all_metrics)
    widths = {
        k: max(len(k), *(len(str(m[k])) for m in all_metrics)) for k in all_metrics[0]
    }
    print("  ".join(k.ljust(widths[k]) for k in widths))
    for m in all_metrics:
        print("  ".join(str(m[k]).ljust(widths[k]) for k in widths))
    return path


def write_disagreements(by_model: dict[str, list[dict]]) -> Path:
    """Write disagreements.md: every mismatch, grouped by model, for review."""
    path = OUT_DIR / "disagreements.md"
    lines = ["# Extraction benchmark — disagreements vs stored qwen3.6 labels\n"]
    for model, entries in by_model.items():
        lines.append(f"\n## {model} — {len(entries)} disagreement(s)\n")
        for e in entries:
            lines.append(
                f"\n### [{e['email_id']}] {e['subject']} — {e['sender']} ({e['date']})\n"
            )
            lines.append(
                f"- priority: ref `{e['ref_priority']}` → pred `{e['pred_priority']}`"
            )
            lines.append(f"- tasks: ref {e['ref_tasks']} → pred {e['pred_tasks']}")
            lines.append(f"- events: ref {e['ref_events']} → pred {e['pred_events']}")
    path.write_text("\n".join(lines) + "\n")
    return path


async def main() -> None:
    """Benchmark every candidate model, then time the baseline on a subset."""
    args = parse_args()
    conn = connect()
    sample = load_sample(conn, args.low_fill, args.seed)
    refs = {row["id"]: load_reference(conn, row) for row in sample}
    dist = Counter(r["priority"] for r in sample)
    print(f"sample: {len(sample)} emails {dict(dist)}", flush=True)
    all_metrics, by_model = [], {}
    for model in args.models:
        print(f"running {model} ...", flush=True)
        results = await run_model(model, sample)
        metrics, disagreements = score_model(model, sample, refs, results)
        all_metrics.append(metrics)
        by_model[model] = disagreements
    if args.baseline_n:
        subset = sample[: args.baseline_n]
        print(f"running baseline {BASELINE} on {len(subset)} emails ...", flush=True)
        results = await run_model(BASELINE, subset)
        metrics, _ = score_model(f"{BASELINE} (self)", subset, refs, results)
        all_metrics.append(metrics)
    print()
    summary = write_summary(all_metrics)
    report = write_disagreements(by_model)
    print(f"\nwrote {summary} and {report}")


if __name__ == "__main__":
    asyncio.run(main())
