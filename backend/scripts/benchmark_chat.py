"""Resumable chat-model benchmark on the synthetic demo mailbox.

Seeds the demo corpus into the job directory (its own DB and Chroma store,
never the real index), then asks every question of scripts/chat_eval.py to
each candidate model through the production prompt (app.chat.build_messages)
and the production Ollama call (streaming, thinking off). Records the answer,
time to first token, total time and tokens/s; scores facts and language.

Follows AGENTS.md "Long-running GPU jobs": state.json saved atomically after
each chunk, re-running resumes, `touch <dir>/STOP` stops after the current
chunk ("stopped cleanly"), the model is always unloaded on exit, a model
whose first answers are far over the speed budget is dropped.

Run from backend/ (in the background, log to a file):

    uv run python -m scripts.benchmark_chat --dir data/benchmark/chat-2026-11-02 \
        > data/benchmark/chat-2026-11-02/run.log 2>&1 &

Report only (no GPU): add `--report`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from datetime import date
from pathlib import Path

import httpx

from app.chat import build_messages
from app.config import settings
from app.db import get_conn
from app.llm.ollama import OllamaClient
from scripts.chat_eval import QUESTIONS, score_answer
from scripts.seed_demo import DemoPaths, point_settings_at_demo, seed

CANDIDATES = [
    "qwen3:8b",
    "gemma4:12b",
    "gemma3:12b-it-qat",
    "gpt-oss:20b",
    "glm-4.7-flash:latest",
    "qwen3.6:latest",
]
CHUNK, CHUNK_MAX_S = 5, 120
# drop a model whose first BUDGET_PROBE answers average over this many seconds
SPEED_BUDGET_S, BUDGET_PROBE = 45.0, 3


class TimedChatClient(OllamaClient):
    """OllamaClient whose chat call also reports timing and token counts."""

    async def chat_timed(self, messages: list[dict]) -> dict:
        """Stream one answer like production; return text and timings."""
        payload = {"model": self.model, "messages": messages, "stream": True}
        if await self._supports_thinking():
            payload["think"] = False
        t0, ttft, parts, last = time.perf_counter(), None, [], {}
        timeout = httpx.Timeout(600, connect=10)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/chat", json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    last = json.loads(line)
                    if err := last.get("error"):
                        raise RuntimeError(f"ollama: {err}")
                    if chunk := last.get("message", {}).get("content", ""):
                        ttft = ttft or time.perf_counter() - t0
                        parts.append(chunk)
        return {
            "answer": "".join(parts),
            "ttft_s": round(ttft or 0.0, 2),
            "total_s": round(time.perf_counter() - t0, 2),
            "eval_count": last.get("eval_count", 0),
            "eval_duration": last.get("eval_duration", 0),
        }

    async def warm_up(self) -> float:
        """Load the model with a tiny prompt; return the load time in seconds."""
        t0 = time.perf_counter()
        await self.chat_timed([{"role": "user", "content": "Say OK."}])
        return round(time.perf_counter() - t0, 1)

    async def unload(self) -> None:
        """Ask Ollama to evict this model from VRAM immediately."""
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": [], "keep_alive": 0},
            )


def parse_args() -> argparse.Namespace:
    """CLI options: job directory, models, repeats, report-only."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--models", nargs="+", default=CANDIDATES)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--report", action="store_true")
    return parser.parse_args()


def load_state(path: Path) -> dict:
    """Saved state, or an empty one."""
    if path.exists():
        return json.loads(path.read_text())
    return {"seed_day": None, "results": {}, "dropped": {}, "load_s": {}}


def save_state(path: Path, state: dict) -> None:
    """Atomic write: tmp file + os.replace."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    os.replace(tmp, path)


def log(msg: str) -> None:
    """One timestamped progress line on stdout (redirected to run.log)."""
    print(f"{time.strftime('%F %T')} {msg}", flush=True)


async def ensure_demo(job_dir: Path, state: dict) -> None:
    """Seed the demo mailbox for today (re-seed if the job resumes another day).

    Results keep the day they were produced on, so scoring stays correct
    across a re-seed.
    """
    paths = DemoPaths(job_dir / "demo")
    today = date.today().isoformat()
    if state["seed_day"] != today or not paths.db.exists():
        log(f"seeding demo mailbox for {today}")
        await seed(reset=True, root=paths.root)
        state["seed_day"] = today
    point_settings_at_demo(paths)


def focus_email_id(key: str) -> int:
    """DB id of a demo corpus email, by its corpus key."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM emails WHERE maildir_file LIKE ?", (f"%/cur/{key}.eml",)
        ).fetchone()
    return row["id"]


def todo_items(done: dict, repeats: int) -> list[tuple[str, dict]]:
    """(item key, question) pairs not answered yet, repeat by repeat."""
    return [
        (f"{q['id']}#{r}", q)
        for r in range(repeats)
        for q in QUESTIONS
        if f"{q['id']}#{r}" not in done
    ]


async def ask(client: TimedChatClient, question: dict, seed_day: str) -> dict:
    """Ask one question through the production prompt; error record on failure."""
    focus = focus_email_id(question["focus"]) if "focus" in question else None
    history = [{"role": "user", "content": question["q"]}]
    try:
        messages = await build_messages(client, history, True, focus)
        result = await client.chat_timed(messages)
    except (httpx.HTTPError, RuntimeError) as exc:
        result = {"error": str(exc)}
    return {**result, "seed_day": seed_day}


def over_budget(done: dict) -> float | None:
    """Mean total time of the first probe answers if over budget, else None."""
    times = [r["total_s"] for r in done.values() if "total_s" in r][:BUDGET_PROBE]
    if len(times) < BUDGET_PROBE:
        return None
    mean = sum(times) / len(times)
    return mean if mean > SPEED_BUDGET_S else None


def _mean(xs: list[float]) -> float:
    """Mean rounded to 0.1, 0.0 for an empty list."""
    return round(sum(xs) / len(xs), 1) if xs else 0.0


def summarize_model(model: str, state: dict) -> dict:
    """One summary row: pass rate, facts, language, speed, failures."""
    scored, ttft, total, toks, errors = [], [], [], [], 0
    by_id = {q["id"]: q for q in QUESTIONS}
    for key, res in state["results"].get(model, {}).items():
        if "error" in res:
            errors += 1
            continue
        q = by_id[key.split("#")[0]]
        scored.append(
            score_answer(q, res["answer"], date.fromisoformat(res["seed_day"]))
        )
        ttft.append(res["ttft_s"])
        total.append(res["total_s"])
        if res["eval_duration"]:
            toks.append(res["eval_count"] / res["eval_duration"] * 1e9)
    n = len(scored) or 1
    return {
        "model": model,
        "answers": len(scored),
        "errors": errors,
        "pass": f"{sum(s['pass'] for s in scored) / n:.0%}",
        "facts": f"{sum(s['facts'] for s in scored) / max(1, sum(s['facts_total'] for s in scored)):.0%}",
        "right_lang": f"{sum(s['lang_ok'] for s in scored) / n:.0%}",
        "ttft_s": _mean(ttft),
        "total_s": _mean(total),
        "tok_s": _mean(toks),
        "load_s": state["load_s"].get(model, ""),
        "dropped": state["dropped"].get(model, ""),
    }


def _answer_lines(model: str, state: dict) -> list[str]:
    """Markdown section with every answer of one model and its score."""
    by_id = {q["id"]: q for q in QUESTIONS}
    lines = [f"\n## {model}\n"]
    for key, res in sorted(state["results"].get(model, {}).items()):
        q = by_id[key.split("#")[0]]
        if "error" in res:
            lines.append(f"\n### {key} — ERROR\n\n{res['error']}\n")
            continue
        s = score_answer(q, res["answer"], date.fromisoformat(res["seed_day"]))
        verdict = (
            "PASS" if s["pass"] else f"FAIL (lang {s['lang']}, missing {s['missing']})"
        )
        lines.append(f"\n### {key} — {verdict} — {res['total_s']} s\n")
        lines.append(f"**Q ({q['lang']}):** {q['q']}\n\n{res['answer'].strip()}\n")
    return lines


def write_report(job_dir: Path, state: dict) -> None:
    """Write summary.md (table) and answers.md (every answer) to the job dir."""
    rows = [summarize_model(m, state) for m in state["results"]]
    if not rows:
        return
    head = list(rows[0])
    table = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    table += ["| " + " | ".join(str(r[k]) for k in head) + " |" for r in rows]
    (job_dir / "summary.md").write_text("\n".join(table) + "\n")
    answers = ["# Chat benchmark answers"]
    for model in state["results"]:
        answers += _answer_lines(model, state)
    (job_dir / "answers.md").write_text("\n".join(answers) + "\n")
    print("\n".join(table))


async def run_model(
    model: str, state: dict, state_path: Path, stop: Path, repeats: int
) -> bool:
    """Answer every pending question with one model; False if STOP was found."""
    done = state["results"].setdefault(model, {})
    todo = todo_items(done, repeats)
    if not todo or model in state["dropped"]:
        return True
    client = TimedChatClient(model)
    try:
        state["load_s"].setdefault(model, await client.warm_up())
        while todo:
            t0, n = time.perf_counter(), 0
            while todo and n < CHUNK and time.perf_counter() - t0 < CHUNK_MAX_S:
                key, question = todo.pop(0)
                done[key] = await ask(client, question, state["seed_day"])
                n += 1
            if (mean := over_budget(done)) is not None:
                state["dropped"][model] = f"first answers took {mean:.0f} s on average"
            save_state(state_path, state)
            log(f"{model}: {len(done)}/{len(QUESTIONS) * repeats}")
            if model in state["dropped"]:
                log(f"{model}: dropped, {state['dropped'][model]}")
                return True
            if stop.exists():
                return False
        return True
    finally:
        await client.unload()


async def run(args: argparse.Namespace) -> None:
    """Run every candidate model until done or STOP."""
    args.dir.mkdir(parents=True, exist_ok=True)
    state_path, stop = args.dir / "state.json", args.dir / "STOP"
    stop.unlink(missing_ok=True)
    state = load_state(state_path)
    try:
        await ensure_demo(args.dir, state)
        save_state(state_path, state)
        for model in args.models:
            log(f"running {model}")
            if not await run_model(model, state, state_path, stop, args.repeats):
                log("STOP file found: stopped cleanly, GPU released. Re-run to resume.")
                return
        log("all models done")
        write_report(args.dir, state)
    finally:
        # retrieval loads the embedding model too: release it as well
        await TimedChatClient(settings.embed_model).unload()


def main() -> None:
    """Entry point: run the benchmark, or only rebuild the report."""
    args = parse_args()
    if args.report:
        write_report(args.dir, load_state(args.dir / "state.json"))
    else:
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
