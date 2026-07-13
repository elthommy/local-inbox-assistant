from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import indexer, rag
from .db import TUNABLE_SETTINGS, get_conn, get_meta, set_meta, triage_filter
from .chat import stream_answer
from .config import settings
from .llm.claude import NOT_CONFIGURED_MESSAGE, ClaudeClient
from .llm.ollama import OllamaClient

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# An email whose extracted tasks are ALL completed counts as handled and
# leaves the priority view; emails without tasks stay until dismissed.
NOT_HANDLED = (
    "(NOT EXISTS(SELECT 1 FROM tasks t WHERE t.email_id = e.id) "
    "OR EXISTS(SELECT 1 FROM tasks t WHERE t.email_id = e.id AND t.done = 0))"
)

EMAIL_LIST_COLUMNS = (
    "e.id, e.sender, e.sender_email, e.subject, e.date_utc, e.unread, "
    "e.priority, e.snippet, e.dismissed, "
    "EXISTS(SELECT 1 FROM muted_senders m "
    "WHERE m.sender_email = LOWER(e.sender_email)) AS muted"
)


def _email_dict(row, include_chips: bool = False, conn=None) -> dict:
    d = dict(row)
    d["unread"] = bool(d["unread"])
    d["dismissed"] = bool(d["dismissed"])
    d["muted"] = bool(d["muted"])
    if include_chips and conn is not None:
        d["tasks"] = [
            dict(t)
            for t in conn.execute(
                "SELECT id, text, due, done FROM tasks WHERE email_id = ?", (row["id"],)
            )
        ]
        d["events"] = [
            dict(ev)
            for ev in conn.execute(
                "SELECT id, title, date, time FROM events WHERE email_id = ?",
                (row["id"],),
            )
        ]
    return d


@router.get("/status")
async def status():
    ollama = OllamaClient()
    ollama_up = await ollama.available()
    models = await ollama.list_models() if ollama_up else []
    with get_conn() as conn:
        indexed = conn.execute("SELECT COUNT(*) c FROM emails").fetchone()["c"]
        last_indexed = get_meta(conn, "last_indexed", "")
    return {
        "ollama": {
            "up": ollama_up,
            "url": settings.ollama_url,
            "chat_model": settings.chat_model,
            "embed_model": settings.embed_model,
            "chat_model_pulled": any(
                m == settings.chat_model or m.startswith(settings.chat_model + ":")
                for m in models
            ),
        },
        "claude": {
            "configured": ClaudeClient().configured(),
            "implemented": False,  # cloud support lands in a later step
        },
        "index": {
            "emails": indexed,
            "chunks": rag.chunk_count(),
            "last_indexed": last_indexed,
            "window_days": settings.window_days,
            "maildir": str(settings.maildir),
            "backend_dir": str(settings.db_path.parent.parent),
            "progress": dict(indexer.progress),
        },
    }


@router.get("/stats")
def stats():
    with get_conn() as conn:
        unread = conn.execute(
            "SELECT COUNT(*) c FROM emails WHERE unread = 1"
        ).fetchone()["c"]
        high = conn.execute(
            f"SELECT COUNT(*) c FROM emails e WHERE e.priority = 'high' "
            f"AND {triage_filter()} AND {NOT_HANDLED}"
        ).fetchone()["c"]
        open_tasks = conn.execute(
            f"SELECT COUNT(*) c FROM tasks t JOIN emails e ON e.id = t.email_id "
            f"WHERE t.done = 0 AND {triage_filter()}"
        ).fetchone()["c"]
        events = conn.execute(
            f"SELECT COUNT(*) c FROM events ev JOIN emails e ON e.id = ev.email_id "
            f"WHERE {triage_filter()}"
        ).fetchone()["c"]
    return {
        "unread": unread,
        "open_tasks": open_tasks,
        "events": events,
        "high_priority": high,
    }


@router.get("/emails")
def list_emails(filter: str = "all", limit: int = 100):
    # dismissed/muted/handled mail stays visible in "all" (flagged, so the UI
    # can dim it and offer undo) but is excluded from the priority view
    where = (
        f"WHERE e.priority = 'high' AND {triage_filter()} AND {NOT_HANDLED}"
        if filter == "priority"
        else ""
    )
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT {EMAIL_LIST_COLUMNS} FROM emails e {where} "
            f"ORDER BY e.date_utc DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_email_dict(r, include_chips=True, conn=conn) for r in rows]


@router.get("/emails/{email_id}")
def get_email(email_id: int):
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {EMAIL_LIST_COLUMNS}, e.body FROM emails e WHERE e.id = ?",
            (email_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "email not found")
        return _email_dict(row, include_chips=True, conn=conn)


@router.get("/tasks")
def list_tasks():
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT t.id, t.email_id, t.text, t.due, t.done, "
            f"e.sender AS source, e.date_utc "
            f"FROM tasks t JOIN emails e ON e.id = t.email_id "
            f"WHERE {triage_filter()} "
            f"ORDER BY t.done ASC, e.date_utc DESC"
        ).fetchall()
    return [{**dict(r), "done": bool(r["done"])} for r in rows]


@router.post("/tasks/{task_id}/toggle")
def toggle_task(task_id: int):
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE tasks SET done = 1 - done WHERE id = ?", (task_id,)
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "task not found")
        row = conn.execute("SELECT done FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return {"id": task_id, "done": bool(row["done"])}


@router.get("/events")
def list_events():
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT ev.id, ev.email_id, ev.title, ev.date, ev.time, "
            f"e.sender AS source, e.date_utc "
            f"FROM events ev JOIN emails e ON e.id = ev.email_id "
            f"WHERE {triage_filter()} "
            f"ORDER BY e.date_utc DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/emails/{email_id}/dismiss")
def dismiss_email(email_id: int):
    """Toggle "not important": hides the email from the priority list and its
    tasks/events from every triage surface. Reversible (soft flag)."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE emails SET dismissed = 1 - dismissed WHERE id = ?", (email_id,)
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "email not found")
        row = conn.execute(
            "SELECT dismissed FROM emails WHERE id = ?", (email_id,)
        ).fetchone()
    return {"id": email_id, "dismissed": bool(row["dismissed"])}


class MuteRequest(BaseModel):
    sender_email: str


@router.post("/senders/mute")
def toggle_mute_sender(req: MuteRequest):
    """Toggle a sender mute. Muted senders are excluded from triage (priority,
    tasks, events, stats, chat context) and skipped by LLM extraction; their
    mail stays in "all" and in semantic search."""
    sender = req.sender_email.strip().lower()
    if not sender:
        raise HTTPException(400, "sender_email required")
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM muted_senders WHERE sender_email = ?", (sender,)
        )
        muted = cur.rowcount == 0
        if muted:
            conn.execute(
                "INSERT INTO muted_senders(sender_email, created_utc) "
                "VALUES(?, datetime('now'))",
                (sender,),
            )
    return {"sender_email": sender, "muted": muted}


@router.get("/senders/muted")
def list_muted_senders():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT sender_email, created_utc FROM muted_senders "
            "ORDER BY created_utc DESC"
        ).fetchall()
    return [dict(r) for r in rows]


class SettingsUpdate(BaseModel):
    window_days: int | None = Field(default=None, ge=1, le=3650)
    extraction_window_days: int | None = Field(default=None, ge=1, le=3650)
    extraction_max_emails: int | None = Field(default=None, ge=1, le=10000)


@router.get("/settings")
def read_settings():
    return {k: getattr(settings, k) for k in TUNABLE_SETTINGS}


@router.post("/settings")
def update_settings(req: SettingsUpdate):
    """Persist UI overrides (meta table) and apply them immediately; they
    take effect from the next indexing run."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    with get_conn() as conn:
        for key, value in updates.items():
            set_meta(conn, f"setting_{key}", str(value))
            setattr(settings, key, value)
    return {k: getattr(settings, k) for k in TUNABLE_SETTINGS}


@router.post("/reindex")
async def reindex():
    if indexer.progress["phase"] not in ("idle", "error"):
        return {"started": False, "progress": dict(indexer.progress)}
    asyncio.create_task(indexer.run_index())
    return {"started": True}


class ChatRequest(BaseModel):
    messages: list[dict]  # [{role, content}], last one is the new user message
    model: str = "ollama"
    use_context: bool = True


@router.post("/chat")
async def chat(req: ChatRequest):
    if not req.messages or req.messages[-1].get("role") != "user":
        raise HTTPException(400, "last message must be from user")

    async def sse():
        if req.model == "claude":
            yield f"event: error\ndata: {json.dumps({'message': NOT_CONFIGURED_MESSAGE})}\n\n"
            return
        try:
            async for chunk in stream_answer(req.messages, req.use_context):
                yield f"data: {json.dumps({'token': chunk})}\n\n"
            yield "event: done\ndata: {}\n\n"
        except Exception as exc:
            log.exception("chat failed")
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
