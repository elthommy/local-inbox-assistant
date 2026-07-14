import os
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.mail.maildir import scan_window, window_start


def make_eml(name: str, dt: datetime, mtime: datetime | None = None):
    p = settings.maildir / name
    p.parent.mkdir(parents=True, exist_ok=True)
    date_hdr = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    p.write_bytes(f"From: x@y.z\nSubject: {name}\nDate: {date_hdr}\n\nbody\n".encode())
    ts = (mtime or dt).timestamp()
    os.utime(p, (ts, ts))
    return p


def days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


def test_window_start_matches_setting():
    delta = datetime.now(timezone.utc) - window_start()
    assert abs(delta.days - settings.window_days) <= 1


def test_scan_keeps_only_recent_dates():
    make_eml("recent.eml", days_ago(5))
    make_eml("old.eml", days_ago(settings.window_days + 30))
    names = [p.name for p in scan_window()]
    assert names == ["recent.eml"]


def test_old_date_with_recent_mtime_is_excluded():
    # freshly synced file containing an old message: mtime passes the cheap
    # pre-filter but the Date header must reject it
    make_eml("old-resynced.eml", days_ago(settings.window_days + 30), mtime=days_ago(0))
    assert scan_window() == []


def test_known_files_are_skipped():
    make_eml("seen.eml", days_ago(2))
    make_eml("new.eml", days_ago(1))
    names = [p.name for p in scan_window(known_files={"seen.eml"})]
    assert names == ["new.eml"]


def test_results_sorted_oldest_first():
    make_eml("newest.eml", days_ago(1))
    make_eml("oldest.eml", days_ago(9))
    make_eml("middle.eml", days_ago(5))
    names = [p.name for p in scan_window()]
    assert names == ["oldest.eml", "middle.eml", "newest.eml"]


def test_undated_file_is_skipped():
    p = settings.maildir / "nodate.eml"
    p.write_bytes(b"From: x@y.z\nSubject: no date\n\nbody\n")
    assert scan_window() == []


def test_subfolders_are_scanned_recursively():
    make_eml("ImapMail/imap.gmail.com/INBOX/cur/inbox.eml", days_ago(2))
    make_eml("ImapMail/imap.orange.fr/INBOX/cur/orange.eml", days_ago(1))
    names = [p.name for p in scan_window()]
    assert names == ["inbox.eml", "orange.eml"]


def test_known_files_keyed_by_relative_path():
    make_eml("a/cur/seen.eml", days_ago(2))
    make_eml("b/cur/new.eml", days_ago(1))
    names = [p.name for p in scan_window(known_files={"a/cur/seen.eml"})]
    assert names == ["new.eml"]


def test_excluded_folders_are_pruned():
    make_eml("Trash/cur/binned.eml", days_ago(1))
    make_eml("[Gmail].sbd/All Mail/cur/dupe.eml", days_ago(1))
    make_eml("INBOX/cur/kept.eml", days_ago(1))
    assert [p.name for p in scan_window()] == ["kept.eml"]


def test_excluding_a_folder_also_prunes_its_sbd_subfolders():
    # subfolders of "Trash" live in "Trash.sbd/"; they go with their parent
    make_eml("Trash.sbd/Keep Me/cur/sub.eml", days_ago(1))
    assert scan_window() == []


def test_non_eml_files_are_ignored():
    make_eml("ok.eml", days_ago(1))
    p = settings.maildir / "index.msf"
    p.write_bytes(b"not a mail")
    assert [p.name for p in scan_window()] == ["ok.eml"]
