"""resolve_event_date: free-text event dates → ISO, anchored on the email date.

Test inputs are real values produced by the extraction LLM on live mail."""

import pytest

from app.db import get_conn
from app.event_dates import backfill_event_dates, resolve_event_date

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
    def test_rewrites_relative_dates_in_place(self):
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
            conn.execute(
                "INSERT INTO events(email_id, title, date) VALUES(?, 'b', '2026-01-01')",
                (eid,),
            )
            conn.execute(
                "INSERT INTO events(email_id, title, date) VALUES(?, 'c', 'prochainement')",
                (eid,),
            )
        assert backfill_event_dates() == 1
        with get_conn() as conn:
            dates = dict(conn.execute("SELECT title, date FROM events").fetchall())
        assert dates["a"] == email_day  # resolved
        assert dates["b"] == "2026-01-01"  # already ISO, untouched
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
