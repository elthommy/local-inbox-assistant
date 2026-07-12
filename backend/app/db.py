"""SQLite storage for parsed emails, extracted tasks/events, and index metadata.

A fresh connection per operation keeps things simple and safe across the
FastAPI event loop, background indexer thread, and the MCP server process
(WAL mode allows concurrent readers with one writer).
"""

import sqlite3
from contextlib import contextmanager

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY,
    maildir_file TEXT UNIQUE NOT NULL,
    message_id TEXT,
    sender TEXT,
    sender_email TEXT,
    subject TEXT,
    date_utc TEXT,               -- ISO 8601, UTC
    unread INTEGER DEFAULT 0,
    snippet TEXT,
    body TEXT,
    in_reply_to TEXT,
    refs TEXT,                   -- References header (space-separated ids)
    priority TEXT,               -- high | medium | low | NULL (not extracted)
    extracted INTEGER DEFAULT 0, -- extraction pass done
    embedded INTEGER DEFAULT 0   -- chunks stored in chroma
);
CREATE INDEX IF NOT EXISTS idx_emails_date ON emails(date_utc DESC);
CREATE INDEX IF NOT EXISTS idx_emails_msgid ON emails(message_id);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    email_id INTEGER REFERENCES emails(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    due TEXT,
    done INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    email_id INTEGER REFERENCES emails(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    date TEXT,                   -- ISO date if parseable, else raw text
    time TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_conn():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_meta(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
