"""LLM extraction pass: priority + actionable tasks + calendar events per email.

Runs only on recent emails (extraction_window_days) because it costs one local
LLM call per email. Results are cached in SQLite (emails.extracted flag)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from .config import settings
from .db import triage_filter
from .event_dates import resolve_event_date
from .llm.ollama import OllamaClient

log = logging.getLogger(__name__)

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "priority": {"type": "string", "enum": ["high", "medium", "low"]},
        "tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "due": {"type": "string"},
                },
                "required": ["text"],
            },
        },
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "date": {"type": "string"},
                    "time": {"type": "string"},
                },
                "required": ["title"],
            },
        },
    },
    "required": ["priority", "tasks", "events"],
}

SYSTEM_PROMPT = """\
You are an email triage assistant. Analyze ONE email and return JSON only.

priority:
- "high": needs the recipient's action or reply soon (direct requests, deadlines, overdue payments, appointments to confirm, urgent personal messages)
- "medium": relevant and possibly actionable, but not urgent (order/travel confirmations, upcoming appointments already booked, CI failures)
- "low": no action needed (newsletters, promotions, notifications, receipts, automated digests)

tasks: concrete actions the RECIPIENT must do, extracted from the email. Short imperative phrasing, in the email's language. "due" is the deadline as written (e.g. "Jul 20", "vendredi", "") if any. Do not invent tasks for informational mail — most emails have none.

events: date/time-bound appointments, meetings, deliveries, flights, deadlines mentioned in the email. "date" as written, "time" as written or "". Most emails have none.

The email may be in French or English. Reply with JSON matching the schema, nothing else."""


def emails_needing_extraction(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Unextracted, non-dismissed, non-muted emails inside the extraction window."""
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=settings.extraction_window_days)
    ).isoformat()
    # dismissed emails and muted senders are skipped entirely: no LLM call.
    # They keep extracted = 0, so un-dismissing/un-muting lets a later run
    # pick them up (while still inside the window).
    return conn.execute(
        f"SELECT * FROM emails e WHERE e.extracted = 0 AND e.date_utc >= ? "
        f"AND {triage_filter()} "
        f"ORDER BY e.date_utc DESC LIMIT ?",
        (cutoff, settings.extraction_max_emails),
    ).fetchall()


async def extract_email(ollama: OllamaClient, row: sqlite3.Row) -> dict:
    """Ask the LLM for priority/tasks/events of one email, as schema-bound JSON."""
    user_msg = (
        f"From: {row['sender']} <{row['sender_email']}>\n"
        f"Subject: {row['subject']}\n"
        f"Date: {row['date_utc']}\n\n"
        f"{row['body'][:4000]}"
    )
    return await ollama.chat_json(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        schema=EXTRACTION_SCHEMA,
    )


def store_extraction(conn: sqlite3.Connection, email_id: int, result: dict) -> None:
    """Persist one extraction result, replacing the email's tasks and events."""
    priority = result.get("priority")
    if priority not in ("high", "medium", "low"):
        priority = "low"
    conn.execute(
        "UPDATE emails SET priority = ?, extracted = 1 WHERE id = ?",
        (priority, email_id),
    )
    conn.execute("DELETE FROM tasks WHERE email_id = ?", (email_id,))
    conn.execute("DELETE FROM events WHERE email_id = ?", (email_id,))
    for task in result.get("tasks", [])[:5]:
        text = (task.get("text") or "").strip()
        if text:
            conn.execute(
                "INSERT INTO tasks(email_id, text, due) VALUES(?, ?, ?)",
                (email_id, text[:200], (task.get("due") or "").strip()[:60]),
            )
    email_row = conn.execute(
        "SELECT date_utc FROM emails WHERE id = ?", (email_id,)
    ).fetchone()
    email_date = email_row["date_utc"] if email_row else ""
    for event in result.get("events", [])[:5]:
        title = (event.get("title") or "").strip()
        if title:
            raw_date = (event.get("date") or "").strip()[:60]
            conn.execute(
                "INSERT INTO events(email_id, title, date, time) VALUES(?, ?, ?, ?)",
                (
                    email_id,
                    title[:200],
                    resolve_event_date(raw_date, email_date or "") or raw_date,
                    (event.get("time") or "").strip()[:60],
                ),
            )


def mark_extraction_failed(conn: sqlite3.Connection, email_id: int) -> None:
    """Mark the email extracted with a default priority so we don't retry forever."""
    conn.execute(
        "UPDATE emails SET priority = 'low', extracted = 1 WHERE id = ?", (email_id,)
    )
