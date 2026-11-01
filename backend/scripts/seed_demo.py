"""Build a self-contained demo mailbox: synthetic .eml files, DB and index.

Everything lands under backend/data/demo/ (or `--dir`), never in the real
index: the script points `settings` at that directory before touching
anything, and only deletes a directory it created itself.

The real scan/parse/embed pipeline runs, so the demo exercises the same code
as a live mailbox. Only the LLM extraction pass is skipped: priorities, tasks
and events are the canned values in demo_corpus, which keeps seeding fast and
the screenshots reproducible. Embedding calls Ollama so chat and RAG work
against the synthetic corpus; `--skip-embed` skips it (no Ollama needed): the
list, priority, task and event views still work, and
`scripts.demo_server` answers chat with scripted replies.

Dates in the corpus are relative to the seeding day, and email times to
today at 08:45 local time (`--clock`), so seed on the day of the screenshots
or recording.

    uv run python -m scripts.seed_demo [--reset] [--skip-embed] [--dir PATH] [--clock HH:MM]

On success it prints the command to launch the app against the demo data.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

from app.config import DATA_DIR, settings
from app.db import get_conn, init_db
from app.extract import store_extraction
from scripts.demo_corpus import rendered_corpus

DEMO_DIR = DATA_DIR / "demo"
# written by the seeder: --reset only deletes a directory carrying it
MARKER_FILE = ".demo-data"
MUTED_DEMO_SENDER = "digest@pydigest.example"
# the story happens at the start of a work day: emails are dated relative to
# today at this local time, so times quoted in bodies match the list view
DEFAULT_CLOCK = "08:45"

# X-Mozilla-Status values the parser reads: 0x0001 is the "read" bit.
_STATUS_READ = "0001"
_STATUS_UNREAD = "0000"


@dataclass(frozen=True)
class DemoPaths:
    """Locations of the demo maildir, DB and Chroma store under one root."""

    root: Path

    @property
    def maildir(self) -> Path:
        """Synthetic Thunderbird-style maildir."""
        return self.root / "maildir"

    @property
    def db(self) -> Path:
        """SQLite database of the demo index."""
        return self.root / "inbox.db"

    @property
    def chroma(self) -> Path:
        """Chroma vector store of the demo index."""
        return self.root / "chroma"


def point_settings_at_demo(paths: DemoPaths) -> None:
    """Redirect settings at the demo directory so the real index is untouched."""
    settings.maildir = paths.maildir
    settings.db_path = paths.db
    settings.chroma_path = paths.chroma


def reset_demo_dir(paths: DemoPaths) -> None:
    """Delete a previous demo directory, refusing one the seeder did not create.

    The default backend/data/demo is always accepted (it predates the marker).
    """
    root = paths.root.resolve()
    if not root.exists():
        return
    if root != DEMO_DIR.resolve() and not (root / MARKER_FILE).exists():
        raise SystemExit(f"refusing to delete {root}: no {MARKER_FILE} marker")
    shutil.rmtree(root)


def story_now(clock: str = DEFAULT_CLOCK) -> datetime:
    """Today at `clock` (HH:MM, local time), as an aware UTC datetime."""
    local = datetime.combine(date.today(), time.fromisoformat(clock)).astimezone()
    return local.astimezone(UTC)


def message_id(key: str) -> str:
    """Stable Message-ID of a corpus entry, so replies can reference it."""
    return f"<{key}@demo.example>"


def _build_message(spec: dict, sent_at: datetime) -> EmailMessage:
    """Render one corpus entry as an EmailMessage (plain text or HTML)."""
    msg = EmailMessage()
    msg["From"] = f"{spec['sender']} <{spec['sender_email']}>"
    msg["To"] = "you@demo.example"
    msg["Subject"] = spec["subject"]
    msg["Date"] = format_datetime(sent_at)
    msg["Message-ID"] = message_id(spec["key"])
    if "reply_to" in spec:
        msg["In-Reply-To"] = message_id(spec["reply_to"])
        msg["References"] = message_id(spec["reply_to"])
    msg["X-Mozilla-Status"] = _STATUS_UNREAD if spec["unread"] else _STATUS_READ
    if "html" in spec:
        msg.set_content("This message requires an HTML-capable reader.")
        msg.add_alternative(spec["html"], subtype="html")
    else:
        msg.set_content(spec["body"])
    return msg


def write_maildir(corpus: list[dict], maildir: Path, now: datetime) -> None:
    """Write every corpus entry as <key>.eml under its maildir folder."""
    for spec in corpus:
        folder = maildir / spec["folder"] / "cur"
        folder.mkdir(parents=True, exist_ok=True)
        sent_at = now - timedelta(hours=spec["hours_ago"])
        path = folder / f"{spec['key']}.eml"
        path.write_bytes(bytes(_build_message(spec, sent_at)))


def apply_extractions(corpus: list[dict]) -> int:
    """Store the canned priority/tasks/events for each seeded email.

    Matched on the .eml path (folder + corpus key): replies in a thread share
    their subject. Returns the number of emails updated so the caller can
    catch a silent mismatch.
    """
    updated = 0
    with get_conn() as conn:
        for spec in corpus:
            row = conn.execute(
                "SELECT id FROM emails WHERE maildir_file = ?",
                (f"{spec['folder']}/cur/{spec['key']}.eml",),
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
            (MUTED_DEMO_SENDER, datetime.now(UTC).isoformat()),
        )


def launch_command(paths: DemoPaths, skip_embed: bool) -> str:
    """Return the shell command that starts the app against the demo data."""
    if skip_embed:
        return (
            f"(cd backend && uv run python -m scripts.demo_server --dir {paths.root}) "
            "& npm run dev"
        )
    return (
        f"INBOX_MAILDIR={paths.maildir} "
        f"INBOX_DB_PATH={paths.db} "
        f"INBOX_CHROMA_PATH={paths.chroma} "
        f"INBOX_EXTRACTION_WINDOW_DAYS=0 "
        f"./start.sh"
    )


async def seed(
    reset: bool,
    skip_embed: bool = False,
    root: Path = DEMO_DIR,
    clock: str = DEFAULT_CLOCK,
) -> int:
    """Create the demo maildir, index it, apply the canned extractions.

    Returns the number of seeded emails.
    """
    paths = DemoPaths(root)
    if reset:
        reset_demo_dir(paths)
    point_settings_at_demo(paths)
    paths.root.mkdir(parents=True, exist_ok=True)
    (paths.root / MARKER_FILE).touch()

    corpus = rendered_corpus(date.today())
    write_maildir(corpus, paths.maildir, story_now(clock))
    init_db()

    # Imported after settings are redirected: the indexer reads them at call
    # time, but keeping the import here makes the ordering requirement obvious.
    from app.indexer import run_index

    how = "no embeddings" if skip_embed else "embeddings via Ollama"
    print(f"indexing {len(corpus)} synthetic emails ({how})...")
    await run_index(do_extract=False, do_embed=not skip_embed)

    updated = apply_extractions(corpus)
    if updated != len(corpus):
        raise SystemExit(
            f"seeded {len(corpus)} emails but only matched {updated} for "
            "extraction — corpus keys and DB rows are out of sync"
        )
    mute_demo_sender()
    return updated


def main() -> None:
    """Parse arguments and run the seeding pass."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the existing demo directory before seeding",
    )
    parser.add_argument(
        "--skip-embed",
        action="store_true",
        help="scan + parse + canned extraction only: no Ollama call",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEMO_DIR,
        help=f"demo data directory (default: {DEMO_DIR})",
    )
    parser.add_argument(
        "--clock",
        default=DEFAULT_CLOCK,
        help=f"local time of 'now' in the story, HH:MM (default: {DEFAULT_CLOCK})",
    )
    args = parser.parse_args()
    root = args.dir.resolve()
    count = asyncio.run(seed(args.reset, args.skip_embed, root, args.clock))
    print(f"done: {count} emails indexed under {root}")
    print("\nStart the app against the demo data with (from the repo root):\n")
    print(f"  {launch_command(DemoPaths(root), args.skip_embed)}\n")


if __name__ == "__main__":
    main()
