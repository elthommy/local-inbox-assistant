import sqlite3

import pytest

from app.db import get_conn, get_meta, init_db, set_meta


def test_init_is_idempotent():
    init_db()
    init_db()
    with get_conn() as conn:
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"emails", "tasks", "events", "meta", "muted_senders"} <= tables


def test_init_migrates_pre_dismissed_db():
    # simulate a DB created before the dismissed column existed
    with get_conn() as conn:
        conn.execute("ALTER TABLE emails DROP COLUMN dismissed")
    init_db()
    with get_conn() as conn:
        conn.execute("INSERT INTO emails(maildir_file) VALUES('a.eml')")
        row = conn.execute("SELECT dismissed FROM emails").fetchone()
    assert row["dismissed"] == 0


def test_meta_roundtrip_and_upsert():
    with get_conn() as conn:
        assert get_meta(conn, "missing", "default") == "default"
        set_meta(conn, "k", "v1")
        assert get_meta(conn, "k") == "v1"
        set_meta(conn, "k", "v2")
        assert get_meta(conn, "k") == "v2"


def test_maildir_file_unique():
    with get_conn() as conn:
        conn.execute("INSERT INTO emails(maildir_file, subject) VALUES('a.eml', 's1')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO emails(maildir_file, subject) VALUES('a.eml', 's2')"
            )


def test_cascade_delete_tasks_and_events():
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO emails(maildir_file) VALUES('a.eml')")
        eid = cur.lastrowid
        conn.execute("INSERT INTO tasks(email_id, text) VALUES(?, 't')", (eid,))
        conn.execute("INSERT INTO events(email_id, title) VALUES(?, 'e')", (eid,))
        conn.execute("DELETE FROM emails WHERE id = ?", (eid,))
        assert conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"] == 0
        assert conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"] == 0
