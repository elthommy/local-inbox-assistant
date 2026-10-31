"""LLM extraction pass: priority + actionable tasks + calendar events per email.

Runs only on recent emails (extraction_window_days) because it costs one local
LLM call per email. Results are cached in SQLite (emails.extracted flag)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime, timedelta

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
You are an email triage assistant for ONE person (the recipient). Analyze ONE email and return JSON only.

Most emails are low priority with no tasks and no events. When unsure, choose "low" and leave tasks and events empty.

priority:
- "high": a real person or organization asks the recipient specifically for something time-sensitive, or missing it has a real cost (e.g. a technician visit to book to restore a service, an overdue payment, a direct question needing a reply soon).
- "medium": relevant to the recipient but not urgent: bookings, reservations, order confirmations, appointments already booked, personal messages from real people, security alerts about the recipient's own accounts or code repositories, account expiry deadlines.
- "low": everything automated or bulk: newsletters, digests, promotions and investment offers (EVEN when they say urgent, last chance, ends tonight, opening in N minutes), petitions and political campaigns, one-time codes, sign-in links, "new sign-in detected" alerts, receipts, bank movement alerts, shipping/delivery notifications (low priority, but their expected delivery date IS an event), notifications about GitHub/forum threads the recipient only follows, and the recipient's own sent emails unless they contain an upcoming appointment.

tasks: only actions the email asks the RECIPIENT to do that matter if not done (book an appointment, pay, reply, activate a new account, claim/keep/renew something before a deadline, pick up an order, update a vulnerable dependency, bring documents). Short imperative phrasing, in the email's language; "due" = deadline as written, or "". NEVER a marketing call to action (buy, invest, sign, subscribe, download the app, read more, take the survey), never "enter/use this code", never for pure notifications.

events: only appointments, bookings, meetings the recipient is invited to (also when mentioned inside a reply thread), order pickup slots (Drive, click & collect), expected deliveries, trips, and account deadlines (claim/keep/activate before a date) that concern the recipient personally, with "date" as written and "time" as written or "". NOT marketing or campaign events, NOT dates inside receipts, bank statements or bills (debit dates), NOT marketing offer or survey end dates, NOT dates already in the past at the email's date.

Examples:
- "Votre code de vérification est 123456, valable 10 minutes" → {"priority":"low","tasks":[],"events":[]}
- "Ouverture de la collecte dans 10 minutes : investissez dès 1 000 € dans notre nouveau projet" → {"priority":"low","tasks":[],"events":[]}
- "Confirmation de votre réservation le 12/03 à 20h00 - 2 personnes" → {"priority":"medium","tasks":[],"events":[{"title":"Réservation restaurant (2 pers.)","date":"12/03","time":"20h00"}]}
- "Votre commande Drive est prête ! Retrait Mar. 14 mars 18h00 - 18h30. Montant payé 52,10€" → {"priority":"medium","tasks":[{"text":"Retirer la commande au Drive","due":"14 mars 18h00"}],"events":[{"title":"Retrait Drive","date":"14 mars","time":"18h00 - 18h30"}]}
- "Un technicien doit intervenir à votre domicile, prenez rendez-vous" → {"priority":"high","tasks":[{"text":"Prendre rendez-vous avec le technicien","due":""}],"events":[]}

The email may be in French or English. Reply with JSON matching the schema, nothing else."""


def emails_needing_extraction(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Unextracted, non-dismissed, non-muted emails inside the extraction window."""
    cutoff = (
        datetime.now(UTC) - timedelta(days=settings.extraction_window_days)
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


def build_user_msg(row: sqlite3.Row) -> str:
    """Format one email row as the user message of the extraction prompt."""
    return (
        f"From: {row['sender']} <{row['sender_email']}>\n"
        f"Subject: {row['subject']}\n"
        f"Date: {row['date_utc']}\n\n"
        f"{row['body'][:4000]}"
    )


async def extract_email(ollama: OllamaClient, row: sqlite3.Row) -> dict:
    """Ask the LLM for priority/tasks/events of one email, as schema-bound JSON."""
    return await ollama.chat_json(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_msg(row)},
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
