"""Scan the Thunderbird maildir for messages within the indexing window.

File mtime is used as a cheap pre-filter (Thunderbird sets maildir file mtimes
at sync time, which is >= the message date, so no in-window message is ever
mtime-older than the window start). The authoritative filter is the parsed
Date header.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import settings
from .parser import parse_date_only


def window_start() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=settings.window_days)


def scan_window(known_files: set[str] | None = None) -> list[Path]:
    """Return maildir files whose Date header falls inside the window,
    excluding already-indexed filenames."""
    known_files = known_files or set()
    start = window_start()
    start_ts = start.timestamp()

    candidates = []
    for p in Path(settings.maildir).iterdir():
        if not p.is_file() or p.name in known_files:
            continue
        try:
            if p.stat().st_mtime < start_ts:
                continue
        except OSError:
            continue
        candidates.append(p)

    result = []
    for p in candidates:
        dt = parse_date_only(p)
        if dt is not None and dt >= start:
            result.append((dt, p))
    result.sort(key=lambda t: t[0])
    return [p for _, p in result]
