from datetime import datetime, timedelta, timezone

from app import indexer, rag
from app.config import settings
from app.db import get_conn, get_meta


def make_eml(name, subject="hello", days_ago=1, body="some body text", msgid=None):
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    date_hdr = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    path = settings.maildir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        f"From: Sender <s@example.com>\nSubject: {subject}\n"
        f"Date: {date_hdr}\nMessage-ID: <{msgid or name}@x>\n\n{body}\n".encode()
    )


def test_store_parsed_ignores_duplicates():
    email = {
        "maildir_file": "a.eml",
        "message_id": "<a@x>",
        "sender": "S",
        "sender_email": "s@x",
        "subject": "s",
        "date_utc": "2026-07-10T00:00:00+00:00",
        "unread": False,
        "snippet": "b",
        "body": "b",
        "in_reply_to": "",
        "refs": "",
    }
    first = indexer._store_parsed([email])
    second = indexer._store_parsed([email])
    assert len(first) == 1
    assert second == []
    with get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM emails").fetchone()["c"] == 1


async def test_label_copy_in_other_folder_indexed_once(fake_embed):
    # Gmail syncs one labeled message into several folders; only the first
    # copy becomes an email row, the other file lands in seen_files
    make_eml("INBOX/cur/a.eml", msgid="same")
    make_eml("Agenda/cur/b.eml", msgid="same")
    await indexer.run_index(do_extract=False)
    await indexer.run_index(do_extract=False)  # rerun must not reparse the copy
    with get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM emails").fetchone()["c"] == 1
        seen = [
            r["maildir_file"]
            for r in conn.execute("SELECT maildir_file FROM seen_files")
        ]
    assert seen in (["INBOX/cur/a.eml"], ["Agenda/cur/b.eml"])
    assert rag.chunk_count() == 1


async def test_emails_stored_with_relative_paths(fake_embed):
    make_eml("ImapMail/host/INBOX/cur/one.eml")
    await indexer.run_index(do_extract=False)
    with get_conn() as conn:
        row = conn.execute("SELECT maildir_file FROM emails").fetchone()
    assert row["maildir_file"] == "ImapMail/host/INBOX/cur/one.eml"


async def test_full_run_parses_embeds_extracts(fake_embed, monkeypatch):
    make_eml("one.eml", subject="invoice", days_ago=2)
    make_eml("two.eml", subject="newsletter", days_ago=3)

    async def fake_extract(ollama, row):
        return {
            "priority": "high" if row["subject"] == "invoice" else "low",
            "tasks": [{"text": "pay it", "due": "soon"}]
            if row["subject"] == "invoice"
            else [],
            "events": [],
        }

    monkeypatch.setattr(indexer, "extract_email", fake_extract)
    await indexer.run_index(do_extract=True)

    assert indexer.progress["phase"] == "idle"
    assert indexer.progress["error"] is None
    with get_conn() as conn:
        emails = conn.execute("SELECT * FROM emails ORDER BY maildir_file").fetchall()
        assert len(emails) == 2
        assert all(e["embedded"] == 1 and e["extracted"] == 1 for e in emails)
        assert {e["priority"] for e in emails} == {"high", "low"}
        assert conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"] == 1
        assert get_meta(conn, "last_indexed") != ""
    assert rag.chunk_count() == 2


async def test_rerun_is_incremental(fake_embed, monkeypatch):
    make_eml("one.eml", days_ago=2)
    calls = []

    async def fake_extract(ollama, row):
        calls.append(row["maildir_file"])
        return {"priority": "low", "tasks": [], "events": []}

    monkeypatch.setattr(indexer, "extract_email", fake_extract)
    await indexer.run_index(do_extract=True)
    make_eml("two.eml", days_ago=1)
    await indexer.run_index(do_extract=True)

    # extraction ran exactly once per email
    assert sorted(calls) == ["one.eml", "two.eml"]
    with get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) c FROM emails").fetchone()["c"] == 2


async def test_skip_extraction_flag(fake_embed):
    make_eml("one.eml", days_ago=2)
    await indexer.run_index(do_extract=False)
    with get_conn() as conn:
        row = conn.execute("SELECT embedded, extracted FROM emails").fetchone()
        assert row["embedded"] == 1
        assert row["extracted"] == 0
        assert get_meta(conn, "last_indexed") != ""


async def test_extraction_failure_marks_email_done(fake_embed, monkeypatch):
    make_eml("bad.eml", days_ago=1)

    async def broken_extract(ollama, row):
        raise RuntimeError("llm exploded")

    monkeypatch.setattr(indexer, "extract_email", broken_extract)
    await indexer.run_index(do_extract=True)
    assert indexer.progress["phase"] == "idle"  # run itself succeeds
    with get_conn() as conn:
        row = conn.execute("SELECT priority, extracted FROM emails").fetchone()
        assert (row["priority"], row["extracted"]) == ("low", 1)


async def test_scan_failure_sets_error_phase(monkeypatch):
    monkeypatch.setattr(settings, "maildir", settings.maildir / "does-not-exist")
    await indexer.run_index(do_extract=False)
    assert indexer.progress["phase"] == "error"
    assert indexer.progress["error"]
    # progress resets on the next successful run
    monkeypatch.undo()


async def test_parse_failure_is_tolerated(fake_embed, monkeypatch):
    make_eml("good.eml", days_ago=1)
    make_eml("crash.eml", days_ago=1)
    real_parse = indexer.parse_eml

    def flaky(path):
        if path.name == "crash.eml":
            raise ValueError("corrupt")
        return real_parse(path)

    monkeypatch.setattr(indexer, "parse_eml", flaky)
    await indexer.run_index(do_extract=False)
    assert indexer.progress["phase"] == "idle"
    with get_conn() as conn:
        files = [
            r["maildir_file"] for r in conn.execute("SELECT maildir_file FROM emails")
        ]
    assert files == ["good.eml"]
