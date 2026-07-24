"""Scan the Thunderbird profile for maildir messages within the indexing window.

Every mailbox folder under the root is walked recursively for .eml files;
folders named in settings.exclude_folders (Trash, Spam, Gmail's "All Mail"
duplicate archive, ...) are pruned. Files are identified by their path
relative to the root, so identical filenames in different folders don't clash.

File mtime is used as a cheap pre-filter (Thunderbird sets maildir file mtimes
at sync time, which is >= the message date, so no in-window message is ever
mtime-older than the window start). The authoritative filter is the parsed
Date header; probe results for out-of-window files are returned to the caller
so it can cache them (skipped_files table) and spare the re-probe next run.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..config import settings
from .parser import parse_date_only

# Progress callback: (phase, done, total). total == 0 means indeterminate.
ProgressFn = Callable[[str, int, int], None]

# How many walked files between two "scanning" progress notifications.
_WALK_NOTIFY_EVERY = 1000


@dataclass
class ScanResult:
    """Outcome of one maildir scan."""

    # In-window files not yet indexed, sorted oldest first.
    new_files: list[Path] = field(default_factory=list)
    # (relative path, ISO date or '') of files probed and found out of window.
    out_of_window: list[tuple[str, str]] = field(default_factory=list)


def window_start() -> datetime:
    """UTC datetime where the indexing window begins (now - window_days)."""
    return datetime.now(UTC) - timedelta(days=settings.window_days)


def rel_name(path: Path) -> str:
    """DB identity of a maildir file: POSIX path relative to the mail root."""
    try:
        return path.relative_to(settings.maildir).as_posix()
    except ValueError:
        return path.name


def _excluded_folders() -> set[str]:
    """Lowercased folder names from settings.exclude_folders (comma-separated)."""
    return {
        name.strip().lower()
        for name in settings.exclude_folders.split(",")
        if name.strip()
    }


def _iter_eml_entries(root: Path) -> Iterator[tuple[Path, float]]:
    """Yield (path, mtime) for .eml files under root, pruning excluded folders.

    A single scandir pass provides the mtime, avoiding a second stat() call
    per file later."""
    if not root.is_dir():
        raise FileNotFoundError(f"maildir root not found: {root}")
    excluded = _excluded_folders()
    dirs = [root]
    while dirs:
        with os.scandir(dirs.pop()) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    # Thunderbird stores a folder's subfolders in "<folder>.sbd/";
                    # strip the suffix so excludes match the folder's display name.
                    if entry.name.removesuffix(".sbd").lower() not in excluded:
                        dirs.append(Path(entry.path))
                elif entry.name.endswith(".eml"):
                    try:
                        yield Path(entry.path), entry.stat().st_mtime
                    except OSError:
                        continue


def _no_progress(phase: str, done: int, total: int) -> None:
    """Default progress sink: ignore updates."""


def _cached_date(iso: str) -> datetime | None:
    """Parse a date_utc string cached in skipped_files ('' -> None)."""
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return None


def _walk_candidates(
    known_files: set[str],
    skipped_dates: dict[str, str],
    start: datetime,
    notify: ProgressFn,
) -> list[tuple[Path, datetime | None]]:
    """Walk the maildir and return probe candidates as (path, known date).

    Files already indexed, mtime-older than the window, or cached as
    out-of-window are dropped here without being opened. The date is non-None
    when a cached probe says the file is now in-window (window was widened)."""
    start_ts = start.timestamp()
    candidates = []
    walked = 0
    for p, mtime in _iter_eml_entries(Path(settings.maildir)):
        walked += 1
        if walked % _WALK_NOTIFY_EVERY == 0:
            notify("scanning", walked, 0)
        rel = rel_name(p)
        if rel in known_files or mtime < start_ts:
            continue
        if rel in skipped_dates:
            dt = _cached_date(skipped_dates[rel])
            if dt is None or dt < start:
                continue
            candidates.append((p, dt))
        else:
            candidates.append((p, None))
    notify("scanning", walked, 0)
    return candidates


def _probe_candidates(
    candidates: list[tuple[Path, datetime | None]],
    start: datetime,
    notify: ProgressFn,
) -> ScanResult:
    """Read the Date header of each candidate and split in/out of window."""
    dated = []
    result = ScanResult()
    for i, (p, dt) in enumerate(candidates):
        if dt is None:
            dt = parse_date_only(p)
        if dt is None or dt < start:
            result.out_of_window.append((rel_name(p), dt.isoformat() if dt else ""))
        else:
            dated.append((dt, p))
        notify("checking", i + 1, len(candidates))
    dated.sort(key=lambda t: t[0])
    result.new_files = [p for _, p in dated]
    return result


def scan_window(
    known_files: set[str] | None = None,
    skipped_dates: dict[str, str] | None = None,
    on_progress: ProgressFn | None = None,
) -> ScanResult:
    """Scan the maildir for files whose Date header falls inside the window.

    known_files (root-relative paths) are already indexed; skipped_dates maps
    already-probed out-of-window files to their cached date. on_progress is
    called with (phase, done, total) as the walk and probe advance."""
    notify = on_progress or _no_progress
    start = window_start()
    candidates = _walk_candidates(
        known_files or set(), skipped_dates or {}, start, notify
    )
    return _probe_candidates(candidates, start, notify)
