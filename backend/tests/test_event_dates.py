"""resolve_event_date: free-text event dates → ISO, anchored on the email date.

Test inputs are real values produced by the extraction LLM on live mail."""

from datetime import date, timedelta

import pytest

from app.db import get_conn
from app.event_dates import (
    backfill_event_dates,
    backfill_task_dues,
    normalize_due,
    normalize_event_date,
    plausible_date,
    resolve_event_date,
)

from .test_extract import insert_email

EMAIL = "2026-07-09T10:00:00+00:00"  # a Thursday


class TestExplicitDates:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2026-07-11", "2026-07-11"),
            ("2026-07-09T15:00:20+00:00", "2026-07-09"),
            ("today (2026-07-01)", "2026-07-01"),
            ("11/07/2026", "2026-07-11"),
            ("07/13/2026", "2026-07-13"),  # US mm/dd — month field > 12
            ("05.07.2026", "2026-07-05"),
            ("2026年7月16日（木）", "2026-07-16"),
            ("9 July 2026", "2026-07-09"),
            ("09 juillet 2026", "2026-07-09"),
            ("8 juil. 2026", "2026-07-08"),
            ("sam. 11 juil. 2026", "2026-07-11"),
            ("Samedi 17 octobre 2026", "2026-10-17"),
            ("13 juillet 2026 0:00", "2026-07-13"),
            ("Saturday 11th July", "2026-07-11"),
            ("July 16, 2026", "2026-07-16"),
            ("31-JUL-2026", "2026-07-31"),  # booking-system style
            ("21-07-2026", "2026-07-21"),
            ("Sep 1, 2026 at 2:58 pm (CEST)", "2026-09-01"),
        ],
    )
    def test_formats(self, raw, expected):
        assert resolve_event_date(raw, EMAIL) == expected

    def test_ranges_use_the_start_date(self):
        raw = "du vendredi 10 juillet au jeudi 16 juillet 2026"
        assert resolve_event_date(raw, EMAIL) == "2026-07-10"


class TestYearInference:
    def test_yearless_dates_take_the_email_year(self):
        assert resolve_event_date("18 juillet", EMAIL) == "2026-07-18"
        assert resolve_event_date("July 15th", EMAIL) == "2026-07-15"
        assert resolve_event_date("through July 9", EMAIL) == "2026-07-09"
        assert resolve_event_date("Lun. 13 juil.", EMAIL) == "2026-07-13"
        assert resolve_event_date("23/06", "2026-07-01T08:00:00") == "2026-06-23"

    def test_far_past_dates_roll_to_next_year(self):
        assert resolve_event_date("3 janvier", "2026-12-20T08:00:00") == "2027-01-03"


class TestRelativeDates:
    def test_today_and_tomorrow(self):
        assert resolve_event_date("aujourd'hui", EMAIL) == "2026-07-09"
        assert resolve_event_date("ce soir", EMAIL) == "2026-07-09"
        assert resolve_event_date("today", EMAIL) == "2026-07-09"
        assert resolve_event_date("demain", EMAIL) == "2026-07-10"
        assert resolve_event_date("tomorrow", EMAIL) == "2026-07-10"
        assert resolve_event_date("après-demain", EMAIL) == "2026-07-11"

    def test_weekday_resolves_on_or_after_the_email_date(self):
        # email sent Thursday Jul 9
        assert resolve_event_date("samedi", EMAIL) == "2026-07-11"
        assert resolve_event_date("vendredi soir", EMAIL) == "2026-07-10"
        assert resolve_event_date("Monday morning", EMAIL) == "2026-07-13"
        # same weekday as the send day means that day, not next week
        assert resolve_event_date("jeudi", EMAIL) == "2026-07-09"

    def test_weekday_in_full_date_does_not_override_the_date(self):
        # "Mercredi 08 juillet" sent on a Tuesday: the written date wins
        assert (
            resolve_event_date("Mercredi 08 juillet", "2026-07-07T09:00:00")
            == "2026-07-08"
        )


class TestUnresolvable:
    @pytest.mark.parametrize("raw", ["", "  ", "prochainement", "cet été"])
    def test_returns_none(self, raw):
        assert resolve_event_date(raw, EMAIL) is None

    def test_missing_or_bad_email_date(self):
        assert resolve_event_date("demain", "") is None
        assert resolve_event_date("demain", "not-a-date") is None


class TestBackfill:
    def test_rewrites_relative_dates_and_drops_past_events(self):
        with get_conn() as conn:
            eid = insert_email(conn)
            row = conn.execute(
                "SELECT date_utc FROM emails WHERE id=?", (eid,)
            ).fetchone()
            email_day = row["date_utc"][:10]
            conn.execute(
                "INSERT INTO events(email_id, title, date) VALUES(?, 'a', 'aujourd''hui')",
                (eid,),
            )
            later = date.fromisoformat(email_day) + timedelta(days=3)
            conn.execute(
                "INSERT INTO events(email_id, title, date) VALUES(?, 'b', ?)",
                (eid, later.isoformat()),
            )
            conn.execute(
                "INSERT INTO events(email_id, title, date) VALUES(?, 'old', '2025-11-05')",
                (eid,),
            )
            conn.execute(
                "INSERT INTO events(email_id, title, date) VALUES(?, 'c', 'prochainement')",
                (eid,),
            )
        assert backfill_event_dates() == 2
        with get_conn() as conn:
            dates = dict(conn.execute("SELECT title, date FROM events").fetchall())
        assert dates["a"] == email_day  # resolved
        assert dates["b"] == later.isoformat()  # already ISO, untouched
        assert "old" not in dates  # already past when the email was sent
        assert dates["c"] == "prochainement"  # unresolvable, untouched

    def test_is_idempotent(self):
        with get_conn() as conn:
            eid = insert_email(conn)
            conn.execute(
                "INSERT INTO events(email_id, title, date) VALUES(?, 'a', 'demain')",
                (eid,),
            )
        assert backfill_event_dates() == 1
        assert backfill_event_dates() == 0


class TestPlausibility:
    def test_window_around_the_send_date(self):
        assert plausible_date("2026-07-08", EMAIL)  # 1 day margin (time zones)
        assert not plausible_date("2026-07-07", EMAIL)
        assert plausible_date("2028-07-01", EMAIL)
        assert not plausible_date("2029-01-01", EMAIL)

    def test_event_dates(self):
        assert normalize_event_date("samedi", EMAIL) == "2026-07-11"
        assert normalize_event_date(" cet été ", EMAIL) == "cet été"  # as written
        assert normalize_event_date("5 novembre 2025", EMAIL) is None  # drop


class TestNormalizeDue:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Jeu. 23 juil. 19h30", "2026-07-23"),
            ("July 30, 2026", "2026-07-30"),
            ("04.08.2026", "2026-08-04"),
            ("vendredi", "2026-07-10"),
            ("2026-07-09T20:11:21+00:00", "2026-07-09"),
            ("octobre", "octobre"),  # month only: kept as written
            ("end of August", "end of August"),
            ("dès que possible", "dès que possible"),
            ("10 minutes", ""),
            ("https://example.com/tickets", ""),
            ("PR #95", ""),
            ("you may pay later", ""),  # "may" the verb, not the month
            ("1er juillet", ""),  # already past at send time
            ("", ""),
        ],
    )
    def test_values(self, raw, expected):
        assert normalize_due(raw, EMAIL) == expected

    def test_backfill(self):
        with get_conn() as conn:
            eid = insert_email(conn)
            for text, due in [("a", "demain"), ("b", "10 minutes"), ("c", "")]:
                conn.execute(
                    "INSERT INTO tasks(email_id, text, due) VALUES(?, ?, ?)",
                    (eid, text, due),
                )
        assert backfill_task_dues() == 2
        assert backfill_task_dues() == 0
        with get_conn() as conn:
            dues = dict(conn.execute("SELECT text, due FROM tasks").fetchall())
        assert dues["a"] != "demain" and len(dues["a"]) == 10
        assert dues["b"] == dues["c"] == ""
