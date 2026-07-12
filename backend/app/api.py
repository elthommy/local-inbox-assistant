from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import indexer, rag
from .db import get_conn, get_meta
from .chat import stream_answer
from .config import settings
from .llm.claude import NOT_CONFIGURED_MESSAGE, ClaudeClient
from .llm.ollama import OllamaClient

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

EMAIL_LIST_COLUMNS = (
    "id, sender, sender_email, subject, date_utc, unread, priority, snippet"
)


def _email_dict(row, include_chips: bool = False, conn=None) -> dict:
    d = dict(row)
    d["unread"] = bool(d["unread"])
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
            "SELECT COUNT(*) c FROM emails WHERE priority = 'high'"
        ).fetchone()["c"]
        open_tasks = conn.execute(
            "SELECT COUNT(*) c FROM tasks WHERE done = 0"
        ).fetchone()["c"]
        events = conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]
    return {
        "unread": unread,
        "open_tasks": open_tasks,
        "events": events,
        "high_priority": high,
    }


@router.get("/emails")
def list_emails(filter: str = "all", limit: int = 100):
    where = "WHERE priority = 'high'" if filter == "priority" else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT {EMAIL_LIST_COLUMNS} FROM emails {where} "
            f"ORDER BY date_utc DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_email_dict(r, include_chips=True, conn=conn) for r in rows]


@router.get("/emails/{email_id}")
def get_email(email_id: int):
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {EMAIL_LIST_COLUMNS}, body FROM emails WHERE id = ?",
            (email_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "email not found")
        return _email_dict(row, include_chips=True, conn=conn)


@router.get("/tasks")
def list_tasks():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT t.id, t.text, t.due, t.done, e.sender AS source, e.date_utc "
            "FROM tasks t JOIN emails e ON e.id = t.email_id "
            "ORDER BY t.done ASC, e.date_utc DESC"
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
            "SELECT ev.id, ev.title, ev.date, ev.time, e.sender AS source, e.date_utc "
            "FROM events ev JOIN emails e ON e.id = ev.email_id "
            "ORDER BY e.date_utc DESC"
        ).fetchall()
    return [dict(r) for r in rows]


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
