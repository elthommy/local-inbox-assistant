"""Scan the Thunderbird profile for maildir messages within the indexing window.

Every mailbox folder under the root is walked recursively for .eml files;
folders named in settings.exclude_folders (Trash, Spam, Gmail's "All Mail"
duplicate archive, ...) are pruned. Files are identified by their path
relative to the root, so identical filenames in different folders don't clash.

File mtime is used as a cheap pre-filter (Thunderbird sets maildir file mtimes
at sync time, which is >= the message date, so no in-window message is ever
mtime-older than the window start). The authoritative filter is the parsed
Date header.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..config import settings
from .parser import parse_date_only


def window_start() -> datetime:
    """UTC datetime where the indexing window begins (now - window_days)."""
    return datetime.now(timezone.utc) - timedelta(days=settings.window_days)


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


def _iter_eml_files(root: Path) -> list[Path]:
    """All .eml files under root, pruning excluded folders during the walk."""
    if not root.is_dir():
        raise FileNotFoundError(f"maildir root not found: {root}")
    excluded = _excluded_folders()
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Thunderbird stores a folder's subfolders in "<folder>.sbd/";
        # strip the suffix so excludes match the folder's display name.
        dirnames[:] = [
            d for d in dirnames if d.removesuffix(".sbd").lower() not in excluded
        ]
        files += [Path(dirpath) / f for f in filenames if f.endswith(".eml")]
    return files


def scan_window(known_files: set[str] | None = None) -> list[Path]:
    """Return maildir files whose Date header falls inside the window,
    excluding already-indexed files (keyed by root-relative path)."""
    known_files = known_files or set()
    start = window_start()
    start_ts = start.timestamp()

    candidates = []
    for p in _iter_eml_files(Path(settings.maildir)):
        if rel_name(p) in known_files:
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
