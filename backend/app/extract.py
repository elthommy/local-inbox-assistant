"""LLM extraction pass: priority + actionable tasks + calendar events per email.

Runs only on recent emails (extraction_window_days) because it costs one local
LLM call per email. Results are cached in SQLite (emails.extracted flag)."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
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
- "medium": relevant to the recipient but not urgent: bookings and reservations for a dated activity (restaurant, tour, show, trip, even when the email calls it an "order"), orders ready for pickup (Drive, click & collect, relay point) with a pickup slot or deadline, appointments already booked, personal messages from real people (including a reply written by a person — a customer-service agent, a property manager, a neighbour — even when it is about an order, a delivery or a request, and anything a friend or relative sends or forwards), security alerts about the recipient's own accounts or code repositories, account expiry deadlines.
- "low": everything automated or bulk: newsletters, digests, promotions and investment offers (EVEN when they say urgent, last chance, ends tonight, opening in N minutes), petitions and political campaigns, one-time codes, sign-in links, account notifications (new sign-in or new connection detected, a device or feature turned on/off, login-method changes, account details updated, terms updates) — the standard "if this wasn't you, secure your account" line does NOT make them important; only an email stating the account WAS compromised or breached is, receipts, bank movement alerts, automated order and payment confirmations for goods, automated order/repair/return status updates, automated shipping and delivery notifications (ordered, shipped, in transit, arriving on <date>, delivered), notifications about GitHub/forum threads the recipient only follows, and the recipient's own sent emails (the email then starts with "[Sent by the recipient]") unless they contain an upcoming appointment.

tasks: only actions the email asks the RECIPIENT to do that matter if not done (book an appointment, pay, reply, activate a new account, claim/keep/renew something before a deadline, pick up an order, update a vulnerable dependency, bring documents). Short imperative phrasing, in the email's language; "due" = deadline as written, or "". NEVER a marketing call to action (buy, invest, sign, subscribe, download the app, read more, take the survey), never "enter/use this code", never for pure notifications. Suggestions ("you can...", "if you wish...", "feel free to...") and practical instructions (arrive 15 minutes early, set your password) are not tasks: only what the recipient is required or explicitly asked to do.

events: only appointments, bookings, meetings the recipient is invited to (also when mentioned inside a reply thread), order pickup slots (Drive, click & collect, a parcel waiting at a relay point or locker until a date), delivery appointments the recipient must be home for (a booked time slot), trips, and account deadlines (claim/keep/activate before a date) that concern the recipient personally, with "date" as written and "time" as written or "". An event needs a concrete date (not "within 4-6 days", not a meeting only proposed) and must be something the recipient booked, ordered, was personally invited to, or must attend. NOT events announced to a mailing list (festivals, webinars, AMAs, conferences, campaign meetings, newsletter agendas), NOT social-network birthday reminders (birthdays and events from the recipient's own calendar notifications ARE events), NOT dates inside receipts, bank statements or bills (debit dates), NOT marketing offer or survey end dates, NOT dates already in the past at the email's date, NOT plain expected delivery dates ("livraison prévue le…", "arrive mercredi", "shipped, arriving…": the parcel comes on its own, nothing to attend).

Examples:
- "Votre code de vérification est 123456, valable 10 minutes" → {"priority":"low","tasks":[],"events":[]}
- "Ouverture de la collecte dans 10 minutes : investissez dès 1 000 € dans notre nouveau projet" → {"priority":"low","tasks":[],"events":[]}
- "Confirmation de votre réservation le 12/03 à 20h00 - 2 personnes" → {"priority":"medium","tasks":[],"events":[{"title":"Réservation restaurant (2 pers.)","date":"12/03","time":"20h00"}]}
- "Votre commande Drive est prête ! Retrait Mar. 14 mars 18h00 - 18h30. Montant payé 52,10€" → {"priority":"medium","tasks":[{"text":"Retirer la commande au Drive","due":"14 mars 18h00"}],"events":[{"title":"Retrait Drive","date":"14 mars","time":"18h00 - 18h30"}]}
- "Expédié : « Lampe de bureau… » Livraison prévue : jeudi 5 mars" → {"priority":"low","tasks":[],"events":[]}
- "Order placed: \\"Desk lamp…\\" Thanks for your order. Arriving March 5" → {"priority":"low","tasks":[],"events":[]}
- "Un technicien doit intervenir à votre domicile, prenez rendez-vous" → {"priority":"high","tasks":[{"text":"Prendre rendez-vous avec le technicien","due":""}],"events":[]}

The email may be in French or English. Reply with JSON matching the schema, nothing else."""

MY_PRIORITIES_MAX = 2000
MY_PRIORITIES_HEADER = (
    "The recipient's own priority rules, written by them. Apply a rule ONLY when it"
    " clearly matches this email's sender and subject; if none matches, ignore this"
    " section completely and judge the email exactly as above. A matching rule"
    ' overrides the priority above and changes ONLY "priority", never tasks or'
    " events:"
)


def system_prompt(my_priorities: str = "") -> str:
    """The extraction system prompt, with the user's "My priorities" rules
    appended when set."""
    rules = my_priorities.strip()[:MY_PRIORITIES_MAX]
    if not rules:
        return SYSTEM_PROMPT
    return f"{SYSTEM_PROMPT}\n\n{MY_PRIORITIES_HEADER}\n{rules}"


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


# Folders holding the mailbox owner's outgoing mail (Thunderbird/Gmail English
# and French names); SQLite LIKE is case-insensitive for ASCII.
SENT_FOLDER_PATTERNS = ("Sent%", "%/Sent%", "Envoy%", "%/Envoy%")
# Must match the wording of SYSTEM_PROMPT's "own sent emails" rule.
OWN_MAIL_MARK = "[Sent by the recipient]"


@dataclass(frozen=True)
class Owner:
    """The mailbox owner's addresses and display names (lower-cased)."""

    emails: frozenset[str] = frozenset()
    names: frozenset[str] = frozenset()

    def sent(self, row: sqlite3.Row) -> bool:
        """Whether this email was written by the owner (any of their addresses,
        or their display name, e.g. a forward from a work account)."""
        return (row["sender_email"] or "").strip().lower() in self.emails or (
            row["sender"] or ""
        ).strip().lower() in self.names


def load_owner(conn: sqlite3.Connection) -> Owner:
    """Learn the owner's identities from the senders of mail in Sent folders."""
    clause = " OR ".join("maildir_file LIKE ?" for _ in SENT_FOLDER_PATTERNS)
    rows = conn.execute(
        f"SELECT DISTINCT sender_email, sender FROM emails WHERE {clause}",
        SENT_FOLDER_PATTERNS,
    ).fetchall()
    emails = {(r["sender_email"] or "").strip().lower() for r in rows}
    names = {(r["sender"] or "").strip().lower() for r in rows}
    return Owner(frozenset(emails - {""}), frozenset(names - {""}))


def build_user_msg(row: sqlite3.Row, own: bool = False) -> str:
    """Format one email row as the user message of the extraction prompt.

    own=True marks the owner's sent mail so the prompt's rule can apply.
    """
    return (
        (f"{OWN_MAIL_MARK}\n" if own else "")
        + f"From: {row['sender']} <{row['sender_email']}>\n"
        f"Subject: {row['subject']}\n"
        f"Date: {row['date_utc']}\n\n"
        f"{row['body'][:4000]}"
    )


async def extract_email(
    ollama: OllamaClient, row: sqlite3.Row, owner: Owner | None = None
) -> dict:
    """Ask the LLM for priority/tasks/events of one email, as schema-bound JSON."""
    own = owner is not None and owner.sent(row)
    return await ollama.chat_json(
        [
            {"role": "system", "content": system_prompt(settings.my_priorities)},
            {"role": "user", "content": build_user_msg(row, own)},
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
