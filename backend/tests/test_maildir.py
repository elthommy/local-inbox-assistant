import os
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.mail import maildir
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
    return datetime.now(UTC) - timedelta(days=n)


def scan_names(**kwargs) -> list[str]:
    return [p.name for p in scan_window(**kwargs).new_files]


def test_window_start_matches_setting():
    delta = datetime.now(UTC) - window_start()
    assert abs(delta.days - settings.window_days) <= 1


def test_scan_keeps_only_recent_dates():
    make_eml("recent.eml", days_ago(5))
    make_eml("old.eml", days_ago(settings.window_days + 30))
    assert scan_names() == ["recent.eml"]


def test_old_date_with_recent_mtime_is_excluded():
    # freshly synced file containing an old message: mtime passes the cheap
    # pre-filter but the Date header must reject it
    make_eml("old-resynced.eml", days_ago(settings.window_days + 30), mtime=days_ago(0))
    assert scan_names() == []


def test_out_of_window_probe_is_reported_for_caching():
    make_eml("old-resynced.eml", days_ago(settings.window_days + 30), mtime=days_ago(0))
    out = scan_window().out_of_window
    assert [name for name, _ in out] == ["old-resynced.eml"]
    assert out[0][1] != ""  # the parsed date is cached alongside


def test_cached_out_of_window_file_is_not_reopened(monkeypatch):
    make_eml("old-resynced.eml", days_ago(settings.window_days + 30), mtime=days_ago(0))
    [(rel, date_utc)] = scan_window().out_of_window

    def boom(path):
        raise AssertionError(f"re-probed {path}")

    monkeypatch.setattr(maildir, "parse_date_only", boom)
    result = scan_window(skipped_dates={rel: date_utc})
    assert result.new_files == []
    assert result.out_of_window == []


def test_cached_file_reenters_window_when_window_grows(monkeypatch):
    make_eml("borderline.eml", days_ago(settings.window_days + 10), mtime=days_ago(0))
    [(rel, date_utc)] = scan_window().out_of_window
    monkeypatch.setattr(settings, "window_days", settings.window_days + 30)
    assert scan_names(skipped_dates={rel: date_utc}) == ["borderline.eml"]


def test_known_files_are_skipped():
    make_eml("seen.eml", days_ago(2))
    make_eml("new.eml", days_ago(1))
    assert scan_names(known_files={"seen.eml"}) == ["new.eml"]


def test_results_sorted_oldest_first():
    make_eml("newest.eml", days_ago(1))
    make_eml("oldest.eml", days_ago(9))
    make_eml("middle.eml", days_ago(5))
    assert scan_names() == ["oldest.eml", "middle.eml", "newest.eml"]


def test_undated_file_is_skipped():
    p = settings.maildir / "nodate.eml"
    p.write_bytes(b"From: x@y.z\nSubject: no date\n\nbody\n")
    result = scan_window()
    assert result.new_files == []
    assert result.out_of_window == [("nodate.eml", "")]


def test_subfolders_are_scanned_recursively():
    make_eml("ImapMail/imap.gmail.com/INBOX/cur/inbox.eml", days_ago(2))
    make_eml("ImapMail/imap.orange.fr/INBOX/cur/orange.eml", days_ago(1))
    assert scan_names() == ["inbox.eml", "orange.eml"]


def test_known_files_keyed_by_relative_path():
    make_eml("a/cur/seen.eml", days_ago(2))
    make_eml("b/cur/new.eml", days_ago(1))
    assert scan_names(known_files={"a/cur/seen.eml"}) == ["new.eml"]


def test_excluded_folders_are_pruned():
    make_eml("Trash/cur/binned.eml", days_ago(1))
    make_eml("[Gmail].sbd/All Mail/cur/dupe.eml", days_ago(1))
    make_eml("INBOX/cur/kept.eml", days_ago(1))
    assert scan_names() == ["kept.eml"]


def test_excluding_a_folder_also_prunes_its_sbd_subfolders():
    # subfolders of "Trash" live in "Trash.sbd/"; they go with their parent
    make_eml("Trash.sbd/Keep Me/cur/sub.eml", days_ago(1))
    assert scan_names() == []


def test_non_eml_files_are_ignored():
    make_eml("ok.eml", days_ago(1))
    p = settings.maildir / "index.msf"
    p.write_bytes(b"not a mail")
    assert scan_names() == ["ok.eml"]


def test_progress_reports_walk_and_probe(monkeypatch):
    monkeypatch.setattr(maildir, "_WALK_NOTIFY_EVERY", 1)
    make_eml("one.eml", days_ago(2))
    make_eml("two.eml", days_ago(1))
    calls = []
    scan_window(on_progress=lambda *args: calls.append(args))
    assert ("scanning", 2, 0) in calls
    assert calls[-1] == ("checking", 2, 2)
