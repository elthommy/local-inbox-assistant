"""localmail MCP server (stdio).

Exposes read-only mail tools over the same SQLite/Chroma index the dashboard
uses. Register with e.g.:

    claude mcp add localmail -- uv --directory /path/to/backend run python mcp_server.py
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from app.db import get_conn, init_db, triage_filter
from app import rag
from app.llm.ollama import OllamaClient

mcp = FastMCP("localmail")


def _email_line(row) -> dict:
    """Compact email descriptor shared by every tool's output."""
    return {
        "id": row["id"],
        "message_id": row["message_id"],
        "sender": row["sender"],
        "sender_email": row["sender_email"],
        "subject": row["subject"],
        "date": row["date_utc"],
        "priority": row["priority"],
    }


@mcp.tool()
async def search_mail(query: str, top_k: int = 5) -> list[dict]:
    """Semantic search over the indexed inbox (last 90 days of Gmail).
    Returns matching emails with a relevant excerpt each."""
    hits = await rag.search_emails(OllamaClient(), query, top_k)
    out = []
    with get_conn() as conn:
        for h in hits:
            row = conn.execute(
                "SELECT * FROM emails WHERE id = ?", (h["email_id"],)
            ).fetchone()
            if row is None:
                continue
            out.append({**_email_line(row), "excerpt": h["text"][:800]})
    return out


@mcp.tool()
def get_thread(message_id: str) -> list[dict]:
    """Fetch an email by Message-ID plus every indexed message in its thread
    (linked via References / In-Reply-To), oldest first, with bodies."""
    message_id = message_id.strip()
    if not message_id.startswith("<"):
        message_id = f"<{message_id}>"
    with get_conn() as conn:
        root = conn.execute(
            "SELECT * FROM emails WHERE message_id = ?", (message_id,)
        ).fetchone()
        if root is None:
            return []
        # thread = all ids referenced by the root + the root itself
        thread_ids = {message_id, *(root["refs"] or "").split(), root["in_reply_to"]}
        thread_ids.discard("")
        rows = conn.execute(
            "SELECT * FROM emails WHERE message_id IN ({}) "
            "OR in_reply_to = ? OR refs LIKE ? ORDER BY date_utc".format(
                ",".join("?" * len(thread_ids))
            ),
            (*thread_ids, message_id, f"%{message_id}%"),
        ).fetchall()
    return [{**_email_line(r), "body": r["body"][:4000]} for r in rows]


@mcp.tool()
def list_tasks(include_done: bool = False) -> list[dict]:
    """List action items extracted from recent emails."""
    done = "" if include_done else "AND t.done = 0"
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT t.id, t.text, t.due, t.done, e.sender AS source, "
            f"e.subject, e.date_utc FROM tasks t "
            f"JOIN emails e ON e.id = t.email_id "
            f"WHERE {triage_filter()} {done} "
            f"ORDER BY e.date_utc DESC"
        ).fetchall()
    return [{**dict(r), "done": bool(r["done"])} for r in rows]


@mcp.tool()
def list_events(limit: int = 20) -> list[dict]:
    """List appointments/deadlines extracted from recent emails."""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT ev.id, ev.title, ev.date, ev.time, e.sender AS source, "
            f"e.subject, e.date_utc FROM events ev "
            f"JOIN emails e ON e.id = ev.email_id "
            f"WHERE {triage_filter()} "
            f"ORDER BY e.date_utc DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    mcp.run()
