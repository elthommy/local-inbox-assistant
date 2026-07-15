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
    embedded INTEGER DEFAULT 0,  -- chunks stored in chroma
    dismissed INTEGER DEFAULT 0  -- user marked "not important"
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

CREATE TABLE IF NOT EXISTS muted_senders (
    sender_email TEXT PRIMARY KEY, -- lowercase
    created_utc TEXT
);

-- Maildir files scanned but not stored as emails: duplicate copies of a
-- message already indexed from another folder (Gmail labels sync the same
-- message into several folders). Listed here so later scans skip them.
CREATE TABLE IF NOT EXISTS seen_files (
    maildir_file TEXT PRIMARY KEY
);

-- Files probed during a scan whose Date header fell outside the indexing
-- window (or was missing). Cached so later scans don't reopen them; a file
-- re-enters the window if window_days grows past its stored date.
CREATE TABLE IF NOT EXISTS skipped_files (
    maildir_file TEXT PRIMARY KEY,
    date_utc TEXT -- ISO date from the header, '' when missing/unparsable
);
"""

# Columns added after the initial release; applied to pre-existing DBs on startup.
MIGRATIONS = [
    (
        "emails",
        "dismissed",
        "ALTER TABLE emails ADD COLUMN dismissed INTEGER DEFAULT 0",
    ),
]


def connect() -> sqlite3.Connection:
    """Open a new WAL-mode connection with row access by column name."""
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create the schema if missing and apply column migrations to old DBs."""
    with connect() as conn:
        conn.executescript(SCHEMA)
        for table, column, ddl in MIGRATIONS:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in cols:
                conn.execute(ddl)
        conn.commit()


def triage_filter(alias: str = "e") -> str:
    """SQL condition: email not dismissed and its sender not muted.

    Applied wherever triage output is surfaced (priority list, tasks, events,
    stats, chat context) — NOT to plain mail listing or search.
    """
    return (
        f"{alias}.dismissed = 0 AND NOT EXISTS "
        f"(SELECT 1 FROM muted_senders m "
        f"WHERE m.sender_email = LOWER({alias}.sender_email))"
    )


@contextmanager
def get_conn():
    """Yield a fresh connection, committing on success and always closing."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# Settings tunable from the UI. Overrides live in the meta table (keys
# "setting_<name>") and take precedence over .env / defaults.
TUNABLE_SETTINGS = ("window_days", "extraction_window_days", "extraction_max_emails")


def apply_setting_overrides() -> None:
    """Load UI-tuned setting overrides from the meta table into settings."""
    with get_conn() as conn:
        for key in TUNABLE_SETTINGS:
            value = get_meta(conn, f"setting_{key}")
            if value:
                setattr(settings, key, int(value))


def get_meta(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    """Read a value from the meta key/value table."""
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Upsert a value into the meta key/value table."""
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
