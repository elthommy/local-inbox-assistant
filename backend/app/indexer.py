"""Incremental indexing pipeline.

Phases: scan maildir -> parse & store new emails -> embed chunks into Chroma
-> LLM extraction on the recent window. Progress is kept in a module-level
dict that /api/status exposes. Only one run at a time."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from . import rag
from .db import get_conn, set_meta
from .extract import (
    emails_needing_extraction,
    extract_email,
    mark_extraction_failed,
    store_extraction,
)
from .llm.ollama import OllamaClient
from .mail.maildir import rel_name, scan_window
from .mail.parser import parse_eml

log = logging.getLogger(__name__)

progress: dict = {"phase": "idle", "done": 0, "total": 0, "error": None}
_lock = asyncio.Lock()

EMAIL_COLUMNS = (
    "maildir_file",
    "message_id",
    "sender",
    "sender_email",
    "subject",
    "date_utc",
    "unread",
    "snippet",
    "body",
    "in_reply_to",
    "refs",
)


def _store_parsed(parsed: list[dict]) -> list[int]:
    """Insert parsed emails, returning rowids of genuinely new ones.

    A message whose Message-ID is already indexed (Gmail labels sync the same
    message into several folders) is not inserted again; its file is recorded
    in seen_files so later scans skip it."""
    new_ids = []
    with get_conn() as conn:
        known_msgids = {
            r["message_id"]
            for r in conn.execute(
                "SELECT message_id FROM emails WHERE message_id != ''"
            )
        }
        for e in parsed:
            msgid = e["message_id"]
            if msgid and msgid in known_msgids:
                conn.execute(
                    "INSERT OR IGNORE INTO seen_files(maildir_file) VALUES(?)",
                    (e["maildir_file"],),
                )
                continue
            cur = conn.execute(
                f"INSERT OR IGNORE INTO emails({','.join(EMAIL_COLUMNS)}) "
                f"VALUES({','.join('?' * len(EMAIL_COLUMNS))})",
                tuple(e[c] for c in EMAIL_COLUMNS),
            )
            if cur.rowcount:
                new_ids.append(cur.lastrowid)
                if msgid:
                    known_msgids.add(msgid)
    return new_ids


async def run_index(do_extract: bool = True) -> None:
    """Run one indexing pass unless one is already in progress."""
    if _lock.locked():
        return
    async with _lock:
        try:
            await _run(do_extract)
        except Exception as exc:  # surfaced in /api/status
            log.exception("indexing failed")
            progress.update(phase="error", error=str(exc))
        else:
            progress.update(phase="idle", error=None)


async def _run(do_extract: bool) -> None:
    """Execute the indexing phases in order: scan/parse, embed, extract."""
    ollama = OllamaClient()
    await _scan_and_parse()
    await _embed_pending(ollama)
    if do_extract:
        await _extract_pending(ollama)
    _mark_indexed()


async def _scan_and_parse() -> None:
    """Scan the maildir window for unknown files, parse and store them."""
    progress.update(phase="scanning", done=0, total=0, error=None)
    with get_conn() as conn:
        known = {
            r["maildir_file"]
            for r in conn.execute(
                "SELECT maildir_file FROM emails "
                "UNION SELECT maildir_file FROM seen_files"
            )
        }
    new_files = await asyncio.to_thread(scan_window, known)

    progress.update(phase="parsing", done=0, total=len(new_files))
    parsed = []
    for i, path in enumerate(new_files):
        try:
            e = await asyncio.to_thread(parse_eml, path)
            if e:
                e["maildir_file"] = rel_name(path)
                parsed.append(e)
        except Exception:
            log.warning("failed to parse %s", path.name)
        progress["done"] = i + 1
    _store_parsed(parsed)


async def _embed_pending(ollama: OllamaClient) -> None:
    """Embed every not-yet-embedded email into Chroma, in small batches."""
    with get_conn() as conn:
        to_embed = [
            dict(r) for r in conn.execute("SELECT * FROM emails WHERE embedded = 0")
        ]
    progress.update(phase="embedding", done=0, total=len(to_embed))
    batch = 16
    for i in range(0, len(to_embed), batch):
        rows = to_embed[i : i + batch]
        await rag.index_emails(ollama, rows)
        with get_conn() as conn:
            conn.executemany(
                "UPDATE emails SET embedded = 1 WHERE id = ?",
                [(r["id"],) for r in rows],
            )
        progress["done"] = min(i + batch, len(to_embed))


async def _extract_pending(ollama: OllamaClient) -> None:
    """Run LLM extraction (priority/tasks/events) on emails that need it."""
    with get_conn() as conn:
        pending = emails_needing_extraction(conn)
    progress.update(phase="extracting", done=0, total=len(pending))
    for i, row in enumerate(pending):
        try:
            result = await extract_email(ollama, row)
            with get_conn() as conn:
                store_extraction(conn, row["id"], result)
        except Exception:
            log.warning("extraction failed for email %s", row["id"])
            with get_conn() as conn:
                mark_extraction_failed(conn, row["id"])
        progress["done"] = i + 1


def _mark_indexed() -> None:
    """Record the completion time of this indexing run."""
    with get_conn() as conn:
        set_meta(conn, "last_indexed", datetime.now(timezone.utc).isoformat())
