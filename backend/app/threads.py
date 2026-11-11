"""Reply threads: group emails by conversation and collapse repeated items.

A reply thread re-sends the same request or appointment in every message
("please confirm your availability", "meeting on the 8th"), so extraction
yields one task/event per message. Surfaces that list tasks and events
(API, chat context, MCP) collapse them at read time: within one thread,
items sharing a date keep only the copy from the newest email. Nothing is
deleted, so this applies to already-stored results without re-parsing.

Threads are linked through Message-ID, In-Reply-To and References (any
shared id joins two emails), so a missing References header in one reply
does not split the thread.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable, Sequence

_MSGID_RE = re.compile(r"<[^<>\s]+>")


def _ids(*headers: str | None) -> list[str]:
    """Message ids (with angle brackets) found in the given header values."""
    return [m for h in headers for m in _MSGID_RE.findall(h or "")]


class _UnionFind:
    """Minimal union-find over string keys."""

    def __init__(self) -> None:
        """Start with every key in its own set."""
        self.parent: dict[str, str] = {}

    def find(self, key: str) -> str:
        """Root of key's set, with path halving."""
        self.parent.setdefault(key, key)
        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def union(self, a: str, b: str) -> None:
        """Merge the sets of a and b."""
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def thread_keys(conn: sqlite3.Connection) -> dict[int, str]:
    """Map every email id to a key shared by all emails of its thread."""
    rows = conn.execute(
        "SELECT id, message_id, in_reply_to, refs FROM emails"
    ).fetchall()
    uf = _UnionFind()
    own_key: dict[int, str] = {}
    for row in rows:
        own = _ids(row["message_id"])
        own_key[row["id"]] = own[0] if own else f"#{row['id']}"
        for other in own[1:] + _ids(row["in_reply_to"], row["refs"]):
            uf.union(own_key[row["id"]], other)
    return {email_id: uf.find(key) for email_id, key in own_key.items()}


def collapse_thread_duplicates(
    rows: Iterable[sqlite3.Row | dict], keys: dict[int, str], date_field: str
) -> list:
    """Keep, per (thread, date) group, only the rows of its newest email.

    rows need email_id, date_utc and date_field; input order is preserved.
    Several items of that newest email with the same date are all kept
    (they are distinct tasks or events, not repeats).
    """
    rows = list(rows)
    newest: dict[tuple[str, str], tuple[str, int]] = {}
    for row in rows:
        group = _group(row, keys, date_field)
        candidate = (row["date_utc"] or "", row["email_id"])
        if group not in newest or candidate > newest[group]:
            newest[group] = candidate
    return [
        row
        for row in rows
        if newest[_group(row, keys, date_field)][1] == row["email_id"]
    ]


def _group(row: sqlite3.Row | dict, keys: dict[int, str], date_field: str):
    """(thread key, date) grouping key of one task/event row."""
    thread = keys.get(row["email_id"], f"#{row['email_id']}")
    return thread, (row[date_field] or "").strip().lower()


def collapse_rows(conn: sqlite3.Connection, rows: Sequence, date_field: str) -> list:
    """collapse_thread_duplicates with thread keys loaded from the DB."""
    if not rows:
        return []
    return collapse_thread_duplicates(rows, thread_keys(conn), date_field)
