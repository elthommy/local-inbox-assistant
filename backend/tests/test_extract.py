from datetime import UTC, datetime, timedelta

from app.config import settings
from app.db import get_conn
from app.extract import (
    emails_needing_extraction,
    mark_extraction_failed,
    store_extraction,
)


def insert_email(conn, *, file="a.eml", days_ago=1, extracted=0, sender_email=""):
    dt = (datetime.now(UTC) - timedelta(days=days_ago)).isoformat()
    cur = conn.execute(
        "INSERT INTO emails(maildir_file, subject, date_utc, extracted, sender_email) "
        "VALUES(?, 's', ?, ?, ?)",
        (file, dt, extracted, sender_email),
    )
    return cur.lastrowid


class TestEmailsNeedingExtraction:
    def test_selects_recent_unextracted(self):
        with get_conn() as conn:
            recent = insert_email(conn, file="recent.eml", days_ago=2)
            insert_email(
                conn, file="old.eml", days_ago=settings.extraction_window_days + 10
            )
            insert_email(conn, file="done.eml", days_ago=1, extracted=1)
        with get_conn() as conn:
            rows = emails_needing_extraction(conn)
        assert [r["id"] for r in rows] == [recent]

    def test_skips_dismissed_and_muted(self):
        with get_conn() as conn:
            kept = insert_email(conn, file="kept.eml", sender_email="ok@x.com")
            dismissed = insert_email(conn, file="dis.eml")
            conn.execute("UPDATE emails SET dismissed = 1 WHERE id = ?", (dismissed,))
            insert_email(conn, file="muted.eml", sender_email="Spam@News.com")
            conn.execute(
                "INSERT INTO muted_senders(sender_email) VALUES('spam@news.com')"
            )
        with get_conn() as conn:
            rows = emails_needing_extraction(conn)
        assert [r["id"] for r in rows] == [kept]

    def test_respects_max_limit(self, monkeypatch):
        monkeypatch.setattr(settings, "extraction_max_emails", 3)
        with get_conn() as conn:
            for i in range(6):
                insert_email(conn, file=f"{i}.eml", days_ago=1)
        with get_conn() as conn:
            assert len(emails_needing_extraction(conn)) == 3


class TestStoreExtraction:
    def test_stores_priority_tasks_events(self):
        with get_conn() as conn:
            eid = insert_email(conn)
            store_extraction(
                conn,
                eid,
                {
                    "priority": "high",
                    "tasks": [{"text": "pay invoice", "due": "Jul 20"}],
                    "events": [
                        {"title": "meeting", "date": "2026-07-14", "time": "14:00"}
                    ],
                },
            )
        with get_conn() as conn:
            email = conn.execute("SELECT * FROM emails WHERE id=?", (eid,)).fetchone()
            assert email["priority"] == "high"
            assert email["extracted"] == 1
            task = conn.execute("SELECT * FROM tasks").fetchone()
            assert (task["text"], task["due"], task["done"]) == (
                "pay invoice",
                "Jul 20",
                0,
            )
            event = conn.execute("SELECT * FROM events").fetchone()
            assert (event["title"], event["date"], event["time"]) == (
                "meeting",
                "2026-07-14",
                "14:00",
            )

    def test_invalid_priority_coerced_to_low(self):
        with get_conn() as conn:
            eid = insert_email(conn)
            store_extraction(
                conn, eid, {"priority": "urgent!!", "tasks": [], "events": []}
            )
            assert (
                conn.execute(
                    "SELECT priority FROM emails WHERE id=?", (eid,)
                ).fetchone()[0]
                == "low"
            )

    def test_blank_and_missing_fields_skipped(self):
        with get_conn() as conn:
            eid = insert_email(conn)
            store_extraction(
                conn,
                eid,
                {
                    "priority": "low",
                    "tasks": [{"text": "  "}, {}],
                    "events": [{"title": ""}],
                },
            )
            assert conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"] == 0
            assert conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"] == 0

    def test_caps_at_five_items_and_truncates(self):
        with get_conn() as conn:
            eid = insert_email(conn)
            store_extraction(
                conn,
                eid,
                {
                    "priority": "medium",
                    "tasks": [{"text": "t" * 500}]
                    + [{"text": f"t{i}"} for i in range(9)],
                    "events": [{"title": f"e{i}"} for i in range(9)],
                },
            )
            assert conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"] == 5
            assert conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"] == 5
            longest = conn.execute("SELECT MAX(LENGTH(text)) m FROM tasks").fetchone()[
                "m"
            ]
            assert longest <= 200

    def test_rerun_replaces_previous_items(self):
        with get_conn() as conn:
            eid = insert_email(conn)
            store_extraction(
                conn, eid, {"priority": "low", "tasks": [{"text": "old"}], "events": []}
            )
            store_extraction(
                conn, eid, {"priority": "low", "tasks": [{"text": "new"}], "events": []}
            )
            rows = conn.execute("SELECT text FROM tasks").fetchall()
            assert [r["text"] for r in rows] == ["new"]


def test_mark_extraction_failed():
    with get_conn() as conn:
        eid = insert_email(conn)
        mark_extraction_failed(conn, eid)
        row = conn.execute(
            "SELECT priority, extracted FROM emails WHERE id=?", (eid,)
        ).fetchone()
        assert (row["priority"], row["extracted"]) == ("low", 1)
    # no longer selected for extraction
    with get_conn() as conn:
        assert emails_needing_extraction(conn) == []
