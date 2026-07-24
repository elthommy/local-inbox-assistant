"""Build a self-contained demo mailbox: synthetic .eml files, DB and index.

Everything lands under backend/data/demo/, never in the real index — the
script points `settings` at that directory before touching anything, and
refuses to delete a path outside it.

The real scan/parse/embed pipeline runs, so the demo exercises the same code
as a live mailbox. Only the LLM extraction pass is skipped: priorities, tasks
and events are the canned values in demo_corpus, which keeps seeding fast and
the screenshots reproducible. Embedding still calls Ollama, so chat and RAG
work against the synthetic corpus.

    uv run python -m scripts.seed_demo [--reset]

On success it prints the command to launch the app against the demo data.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid

from app.config import DATA_DIR, settings
from app.db import get_conn, init_db
from app.extract import store_extraction
from scripts.demo_corpus import DEMO_EMAILS

DEMO_DIR = DATA_DIR / "demo"
DEMO_MAILDIR = DEMO_DIR / "maildir"
DEMO_DB = DEMO_DIR / "inbox.db"
DEMO_CHROMA = DEMO_DIR / "chroma"

# X-Mozilla-Status values the parser reads: 0x0001 is the "read" bit.
_STATUS_READ = "0001"
_STATUS_UNREAD = "0000"


def point_settings_at_demo() -> None:
    """Redirect settings at the demo directory so the real index is untouched."""
    settings.maildir = DEMO_MAILDIR
    settings.db_path = DEMO_DB
    settings.chroma_path = DEMO_CHROMA


def reset_demo_dir() -> None:
    """Delete the demo directory, refusing any path outside DATA_DIR/demo."""
    resolved = DEMO_DIR.resolve()
    if resolved.parent != DATA_DIR.resolve() or resolved.name != "demo":
        raise SystemExit(f"refusing to delete unexpected path: {resolved}")
    shutil.rmtree(resolved, ignore_errors=True)


def _build_message(spec: dict, sent_at: datetime) -> EmailMessage:
    """Render one corpus entry as an EmailMessage (plain text or HTML)."""
    msg = EmailMessage()
    msg["From"] = f"{spec['sender']} <{spec['sender_email']}>"
    msg["To"] = "demo@localhost"
    msg["Subject"] = spec["subject"]
    msg["Date"] = format_datetime(sent_at)
    msg["Message-ID"] = make_msgid(domain="demo.local")
    msg["X-Mozilla-Status"] = _STATUS_UNREAD if spec["unread"] else _STATUS_READ
    if "html" in spec:
        msg.set_content("This message requires an HTML-capable reader.")
        msg.add_alternative(spec["html"], subtype="html")
    else:
        msg.set_content(spec["body"])
    return msg


def write_maildir(now: datetime) -> None:
    """Write every corpus entry as an .eml file under the demo maildir."""
    for spec in DEMO_EMAILS:
        folder = DEMO_MAILDIR / spec["folder"] / "cur"
        folder.mkdir(parents=True, exist_ok=True)
        sent_at = now - timedelta(hours=spec["hours_ago"])
        path = folder / f"{spec['key']}.eml"
        path.write_bytes(bytes(_build_message(spec, sent_at)))


def apply_extractions() -> int:
    """Store the canned priority/tasks/events for each seeded email.

    Matched on subject, which is unique across the corpus. Returns the number
    of emails updated so the caller can catch a silent mismatch.
    """
    updated = 0
    with get_conn() as conn:
        for spec in DEMO_EMAILS:
            row = conn.execute(
                "SELECT id FROM emails WHERE subject = ?", (spec["subject"],)
            ).fetchone()
            if row is None:
                continue
            store_extraction(conn, row["id"], spec["extraction"])
            updated += 1
    return updated


def mute_demo_sender() -> None:
    """Mute one newsletter sender so the muted-senders UI is not empty."""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO muted_senders(sender_email, created_utc) "
            "VALUES(?, ?)",
            ("digest@pythonweekly.example", datetime.now(UTC).isoformat()),
        )


def launch_command() -> str:
    """Return the shell command that starts the app against the demo data."""
    return (
        f"INBOX_MAILDIR={DEMO_MAILDIR} "
        f"INBOX_DB_PATH={DEMO_DB} "
        f"INBOX_CHROMA_PATH={DEMO_CHROMA} "
        f"INBOX_EXTRACTION_WINDOW_DAYS=0 "
        f"./start.sh"
    )


async def seed(reset: bool) -> None:
    """Create the demo maildir, index it, and apply the canned extractions."""
    if reset:
        reset_demo_dir()
    point_settings_at_demo()
    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    write_maildir(datetime.now(UTC))
    init_db()

    # Imported after settings are redirected: the indexer reads them at call
    # time, but keeping the import here makes the ordering requirement obvious.
    from app.indexer import run_index

    print(f"indexing {len(DEMO_EMAILS)} synthetic emails (embeddings via Ollama)...")
    await run_index(do_extract=False)

    updated = apply_extractions()
    if updated != len(DEMO_EMAILS):
        raise SystemExit(
            f"seeded {len(DEMO_EMAILS)} emails but only matched {updated} for "
            "extraction — corpus subjects and DB rows are out of sync"
        )
    mute_demo_sender()

    print(f"done: {updated} emails indexed under {DEMO_DIR}")
    print("\nStart the app against the demo data with:\n")
    print(f"  {launch_command()}\n")


def main() -> None:
    """Parse arguments and run the seeding pass."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the existing demo directory before seeding",
    )
    args = parser.parse_args()
    asyncio.run(seed(args.reset))


if __name__ == "__main__":
    main()
