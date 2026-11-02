"""Resumable retrieval benchmark: which embedding model finds the right email?

For each embedding configuration (model + query/document prefixes), embeds
the synthetic demo mailbox plus a seeded sample of the real mailbox's
emails as distractors, then checks for every question of
scripts/chat_eval.py that has a `source` whether that demo email is among
the top emails the chat would see (same grouping as rag.search_emails).
Cross-language questions (English question, French email or the reverse)
are reported separately: they are the case that motivated this benchmark.

Real emails stay local: they are only embedded, never printed; the report
names demo emails only. A real email that happens to answer a question
counts as a miss for every model alike.

Follows AGENTS.md "Long-running GPU jobs": one configuration per chunk,
saved atomically to state.json; `touch <dir>/STOP` stops after the current
one ("stopped cleanly"); the model is unloaded after each configuration and
on exit. Run from backend/:

    uv run python -m scripts.benchmark_retrieval --dir data/benchmark/retrieval-2026-11-02 \
        > data/benchmark/retrieval-2026-11-02.log 2>&1 &
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sqlite3
import time
from pathlib import Path

import httpx
import numpy as np

from app.config import DATA_DIR, settings
from app.lang import detect_language
from app.rag import email_to_chunks
from scripts.chat_eval import QUESTIONS
from scripts.seed_demo import DemoPaths, seed

# (label, model, query prefix, document prefix)
CONFIGS = [
    ("nomic-embed-text (no prefix, before)", "nomic-embed-text", "", ""),
    ("nomic-embed-text", "nomic-embed-text", "search_query: ", "search_document: "),
    (
        "nomic-embed-text-v2-moe",
        "nomic-embed-text-v2-moe",
        "search_query: ",
        "search_document: ",
    ),
    ("bge-m3", "bge-m3", "", ""),
    ("snowflake-arctic-embed2", "snowflake-arctic-embed2", "query: ", ""),
    (
        "qwen3-embedding:0.6b",
        "qwen3-embedding:0.6b",
        "Instruct: Given a question about the user's emails, retrieve the "
        "email passages that answer it\nQuery: ",
        "",
    ),
    (
        "embeddinggemma",
        "embeddinggemma",
        "task: search result | query: ",
        "title: none | text: ",
    ),
]
TOP_K = settings.rag_top_k
BATCH = 32


def parse_args() -> argparse.Namespace:
    """CLI options: job directory, distractor count, report-only."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--distractors", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--report", action="store_true")
    return parser.parse_args()


def log(msg: str) -> None:
    """One timestamped progress line on stdout (redirected to the log)."""
    print(f"{time.strftime('%F %T')} {msg}", flush=True)


def save_json(path: Path, data: dict) -> None:
    """Atomic write: tmp file + os.replace."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    os.replace(tmp, path)


def _rows(db: Path, where: str = "1") -> list[dict]:
    """Email rows of a SQLite index as dicts."""
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(f"SELECT * FROM emails WHERE {where}")]
    conn.close()
    return rows


async def load_corpus(job_dir: Path, distractors: int, seed_n: int) -> list[dict]:
    """Demo emails (tagged with their corpus key) + sampled real emails."""
    paths = DemoPaths(job_dir / "demo")
    if not paths.db.exists():
        await seed(reset=True, skip_embed=True, root=paths.root)
    demo = _rows(paths.db)
    for r in demo:
        r["key"] = Path(r["maildir_file"]).stem
        r["id"] = f"demo:{r['key']}"
    real = _rows(DATA_DIR / "inbox.db", "body IS NOT NULL AND body != ''")
    real = random.Random(seed_n).sample(real, min(distractors, len(real)))
    for r in real:
        r["key"], r["id"] = None, f"real:{r['id']}"
    return demo + real


def build_chunks(corpus: list[dict]) -> tuple[list[str], list[str]]:
    """(email id per chunk, chunk text), chunked exactly like the app."""
    owners, docs = [], []
    for row in corpus:
        _, chunk_docs, _ = email_to_chunks(row)
        owners += [row["id"]] * len(chunk_docs)
        docs += chunk_docs
    return owners, docs


async def embed(client: httpx.AsyncClient, model: str, texts: list[str]) -> np.ndarray:
    """Embed texts in batches; rows are L2-normalised for cosine similarity."""
    out = []
    for i in range(0, len(texts), BATCH):
        r = await client.post(
            f"{settings.ollama_url}/api/embed",
            json={"model": model, "input": texts[i : i + BATCH]},
        )
        r.raise_for_status()
        out += r.json()["embeddings"]
    vecs = np.asarray(out, dtype=np.float32)
    return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)


def top_emails(scores: np.ndarray, owners: list[str], k: int = TOP_K) -> list[str]:
    """Best k distinct emails from chunk scores, like rag.search_emails."""
    seen: list[str] = []
    for idx in np.argsort(-scores)[: k * 4]:
        if owners[idx] not in seen:
            seen.append(owners[idx])
    return seen[:k]


def rank_of(scores: np.ndarray, owners: list[str], target: str) -> int:
    """1-based rank of an email among distinct emails by best chunk score."""
    best: dict[str, float] = {}
    for s, o in zip(scores.tolist(), owners):
        best[o] = max(best.get(o, -2.0), s)
    ordered = sorted(best, key=best.get, reverse=True)
    return ordered.index(target) + 1


def retrieval_questions(corpus: list[dict]) -> list[dict]:
    """Questions with a source, flagged cross-language against that email."""
    lang = {r["key"]: detect_language(r["body"]) for r in corpus if r["key"]}
    out = []
    for q in QUESTIONS:
        src = q.get("source", [None])[0]
        if src in lang:
            out.append({**q, "target": f"demo:{src}", "cross": lang[src] != q["lang"]})
    return out


async def run_config(config: tuple, corpus: list[dict], questions: list[dict]) -> dict:
    """Embed the corpus and questions with one configuration; score each question."""
    label, model, q_prefix, d_prefix = config
    owners, docs = build_chunks(corpus)
    async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=10)) as client:
        try:
            t0 = time.perf_counter()
            doc_vecs = await embed(client, model, [d_prefix + d for d in docs])
            doc_s = time.perf_counter() - t0
            q_vecs = await embed(client, model, [q_prefix + q["q"] for q in questions])
        finally:
            await client.post(
                f"{settings.ollama_url}/api/embed",
                json={"model": model, "input": [], "keep_alive": 0},
            )
    per_q = {}
    for q, vec in zip(questions, q_vecs):
        scores = doc_vecs @ vec
        per_q[q["id"]] = {
            "hit": q["target"] in top_emails(scores, owners),
            "rank": rank_of(scores, owners, q["target"]),
            "cross": q["cross"],
        }
    return {
        "label": label,
        "chunks": len(docs),
        "chunks_per_s": round(len(docs) / doc_s, 1),
        "questions": per_q,
    }


def _rate(questions: list[dict]) -> str:
    """'hits/total' for a list of per-question results."""
    return f"{sum(q['hit'] for q in questions)}/{len(questions)}"


def summary_row(res: dict) -> dict:
    """Hit rate in the top k (all / cross-language / same language), MRR, speed."""
    qs = list(res["questions"].values())
    cross = [q for q in qs if q["cross"]]
    same = [q for q in qs if not q["cross"]]
    return {
        "config": res["label"],
        f"top{TOP_K}_all": _rate(qs),
        "cross_lang": _rate(cross),
        "same_lang": _rate(same),
        "mrr": round(sum(1 / q["rank"] for q in qs) / len(qs), 2),
        "chunks_per_s": res["chunks_per_s"],
        "missed": ", ".join(k for k, q in res["questions"].items() if not q["hit"]),
    }


def write_report(job_dir: Path, state: dict) -> None:
    """Write summary.md with one row per finished configuration."""
    rows = [summary_row(r) for r in state["results"].values()]
    if not rows:
        return
    head = list(rows[0])
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(str(r[k]) for k in head) + " |" for r in rows]
    (job_dir / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


async def run(args: argparse.Namespace) -> None:
    """Run every unfinished configuration until done or STOP."""
    args.dir.mkdir(parents=True, exist_ok=True)
    state_path, stop = args.dir / "state.json", args.dir / "STOP"
    stop.unlink(missing_ok=True)
    state = (
        json.loads(state_path.read_text()) if state_path.exists() else {"results": {}}
    )
    corpus = await load_corpus(args.dir, args.distractors, args.seed)
    questions = retrieval_questions(corpus)
    log(f"corpus: {len(corpus)} emails, {len(questions)} questions")
    for config in CONFIGS:
        if config[0] in state["results"]:
            continue
        log(f"running {config[0]}")
        state["results"][config[0]] = await run_config(config, corpus, questions)
        save_json(state_path, state)
        log(f"{config[0]}: {summary_row(state['results'][config[0]])}")
        if stop.exists():
            log("STOP file found: stopped cleanly, GPU released. Re-run to resume.")
            return
    log("all configs done")
    write_report(args.dir, state)


def main() -> None:
    """Entry point: run the benchmark, or only rebuild the report."""
    args = parse_args()
    if args.report:
        write_report(args.dir, json.loads((args.dir / "state.json").read_text()))
    else:
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
