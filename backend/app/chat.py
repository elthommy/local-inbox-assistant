"""RAG chat orchestration: retrieve relevant email chunks, add open tasks and
upcoming events, and stream the local model's answer."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime

from . import rag
from .config import settings
from .db import get_conn, triage_filter
from .llm.ollama import OllamaClient

SYSTEM_NO_CONTEXT = """\
You are a helpful assistant inside a local inbox dashboard. Inbox context is
currently DISABLED, so you cannot see any of the user's emails. If asked about
their mail, tasks or schedule, say that inbox context is off and can be enabled
with the "inbox context" toggle. Answer general questions normally. Reply in
the language the user writes in."""

SYSTEM_WITH_CONTEXT = """\
You are an inbox assistant with access to excerpts of the user's real mailbox
(retrieved by semantic search), plus their current task and event lists that
were extracted from recent emails. Today is {today}.

Answer using ONLY this context; if it does not contain the answer, say so
rather than inventing details. Quote senders/dates when useful. Be concise and
practical. Reply in the language the user writes in (mailbox is mostly French).
You may use light Markdown formatting (bold, bullet lists, inline code); avoid
headings and tables unless they genuinely help.
{email_focus}
## Retrieved email excerpts
{excerpts}

## Open tasks
{tasks}

## Upcoming events
{events}"""

EMAIL_FOCUS_BLOCK = """
## Email in focus
The user selected this email in the dashboard; "this email" refers to it.
When asked to summarize it, give a short summary (a few "-" bullets covering
who wrote, what it says, and any action needed or deadline), written in the
language the email itself is written in — not the language of the summarize
request.

From: {sender} <{sender_email}>
Date: {date}
Subject: {subject}

{body}
"""

# keep the pinned email within a modest share of the model's context window
FOCUS_BODY_MAX_CHARS = 8000


def _format_context_blocks() -> tuple[str, str]:
    with get_conn() as conn:
        tasks = conn.execute(
            f"SELECT t.text, t.due, e.sender FROM tasks t "
            f"JOIN emails e ON e.id = t.email_id "
            f"WHERE t.done = 0 AND {triage_filter()} "
            f"ORDER BY e.date_utc DESC LIMIT 20"
        ).fetchall()
        events = conn.execute(
            f"SELECT ev.title, ev.date, ev.time, e.sender FROM events ev "
            f"JOIN emails e ON e.id = ev.email_id "
            f"WHERE {triage_filter()} "
            f"ORDER BY e.date_utc DESC LIMIT 20"
        ).fetchall()
    task_lines = [
        f"- {t['text']}" + (f" (due {t['due']})" if t["due"] else "") + f" [from {t['sender']}]"
        for t in tasks
    ] or ["(none)"]
    event_lines = [
        f"- {ev['title']} — {ev['date']} {ev['time']}".rstrip() + f" [from {ev['sender']}]"
        for ev in events
    ] or ["(none)"]
    return "\n".join(task_lines), "\n".join(event_lines)


def _format_email_focus(email_id: int) -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT sender, sender_email, subject, date_utc, body, snippet "
            "FROM emails WHERE id = ?",
            (email_id,),
        ).fetchone()
    if row is None:
        return ""
    body = (row["body"] or row["snippet"] or "").strip()
    if len(body) > FOCUS_BODY_MAX_CHARS:
        body = body[:FOCUS_BODY_MAX_CHARS] + "\n[… truncated …]"
    return EMAIL_FOCUS_BLOCK.format(
        sender=row["sender"] or "?",
        sender_email=row["sender_email"] or "?",
        date=row["date_utc"] or "?",
        subject=row["subject"] or "(no subject)",
        body=body or "(empty body)",
    )


async def build_messages(
    ollama: OllamaClient,
    history: list[dict],
    use_context: bool,
    email_id: int | None = None,
) -> list[dict]:
    """history: [{"role": "user"|"assistant", "content": str}], last item is
    the new user message. email_id pins one email's full text into the
    context (the "summarize" button), even when inbox context is off — the
    user explicitly picked that email."""
    email_focus = _format_email_focus(email_id) if email_id is not None else ""
    if not use_context and not email_focus:
        system = SYSTEM_NO_CONTEXT
    else:
        if use_context:
            query = history[-1]["content"]
            hits = await rag.search_emails(ollama, query, settings.rag_top_k)
            excerpts = (
                "\n\n---\n\n".join(h["text"][:1500] for h in hits)
                if hits
                else "(no relevant emails found)"
            )
            tasks_block, events_block = _format_context_blocks()
        else:
            excerpts = "(inbox context is off — only the email in focus is visible)"
            tasks_block = events_block = "(inbox context is off)"
        system = SYSTEM_WITH_CONTEXT.format(
            today=datetime.now().strftime("%A %d %B %Y"),
            email_focus=email_focus,
            excerpts=excerpts,
            tasks=tasks_block,
            events=events_block,
        )
    return [{"role": "system", "content": system}, *history[-12:]]


async def stream_answer(
    history: list[dict], use_context: bool, email_id: int | None = None
) -> AsyncIterator[str]:
    ollama = OllamaClient()
    messages = await build_messages(ollama, history, use_context, email_id)
    async for chunk in ollama.chat_stream(messages):
        yield chunk
