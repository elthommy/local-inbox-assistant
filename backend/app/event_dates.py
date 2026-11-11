"""Resolve free-text event dates to ISO YYYY-MM-DD.

The extraction LLM stores event dates "as written" — French or English month
names ("18 juillet", "July 15th"), bare weekdays ("vendredi soir"), relative
words ("demain", "today"), numeric forms (dd/mm/yyyy, mm/dd/yyyy, dd.mm.yyyy)
or ISO. Relative wordings are anchored on the day the source email was sent:
a weekday resolves to the first such day on/after the send date.

Normalization happens at storage time (store_extraction) so every surface —
Events tab, MCP tools, chat context — agrees on when an event actually is.
Task dues get the same treatment (normalize_due), and dates already past when
the email was sent are dropped. `python -m app.event_dates` (from backend/)
backfills already-stored events and tasks.

src/utils.js keeps a lighter mirror of this logic as a display-time fallback.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

# token tables are accent-folded (see _fold); Monday = 0 like date.weekday()
_MONTHS = {
    1: ["janvier", "janv", "january", "jan"],
    2: ["fevrier", "fevr", "fev", "february", "feb"],
    3: ["mars", "march"],
    4: ["avril", "avr", "april", "apr"],
    5: ["mai", "may"],
    6: ["juin", "june", "jun"],
    7: ["juillet", "juil", "july", "jul"],
    8: ["aout", "august", "aug"],
    9: ["septembre", "sept", "september", "sep"],
    10: ["octobre", "october", "oct"],
    11: ["novembre", "november", "nov"],
    12: ["decembre", "december", "dec"],
}
_WEEKDAYS = {
    0: ["lundi", "lun", "monday", "mon"],
    1: ["mardi", "mar", "tuesday", "tues", "tue"],
    2: ["mercredi", "mer", "wednesday", "wed"],
    3: ["jeudi", "jeu", "thursday", "thurs", "thu"],
    4: ["vendredi", "ven", "friday", "fri"],
    5: ["samedi", "sam", "saturday", "sat"],
    6: ["dimanche", "dim", "sunday", "sun"],
}

_MONTH_NUM = {tok: n for n, toks in _MONTHS.items() for tok in toks}
_WEEKDAY_NUM = {tok: n for n, toks in _WEEKDAYS.items() for tok in toks}


def _alt(tokens) -> str:
    """Regex alternation of tokens, longest first so 'juillet' beats 'juil'."""
    return "|".join(sorted(tokens, key=len, reverse=True))


_ISO_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})(?!\d)")
_JP_RE = re.compile(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日")
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_NUMERIC_RE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](20\d{2})\b")
_NUMERIC_SHORT_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})\b")
_DAY_SUFFIX = r"(?:st|nd|rd|th|er)?"
# "18 juillet", and "31-JUL-2026" as some booking systems write it
_DAY_MONTH_RE = re.compile(
    rf"\b(\d{{1,2}}){_DAY_SUFFIX}(?:\s+|-)({_alt(_MONTH_NUM)})\b"
)
_MONTH_DAY_RE = re.compile(rf"\b({_alt(_MONTH_NUM)})\.?,?\s+(\d{{1,2}}){_DAY_SUFFIX}\b")
_TODAY_RE = re.compile(r"\b(aujourd'?hui|ce soir|today|tonight|this evening)\b")
_TOMORROW_RE = re.compile(r"\b(demain|tomorrow)\b")
_AFTER_TOMORROW_RE = re.compile(r"\bapres[- ]demain\b")
_WEEKDAY_RE = re.compile(rf"\b({_alt(_WEEKDAY_NUM)})\b")


def _fold(s: str) -> str:
    """Lowercase and strip accents so 'Août' matches 'aout'."""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def _valid(year: int, month: int, day: int) -> date | None:
    """Build a date, or None when the combination doesn't exist."""
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _with_inferred_year(month: int, day: int, raw: str, email_day: date) -> date | None:
    """Date for a day/month, taking the year from raw or the email's send date."""
    m = _YEAR_RE.search(raw)
    if m:
        return _valid(int(m.group(1)), month, day)
    # no explicit year: assume the email's; a date far in the past relative to
    # the send date ("3 janvier" in a December email) means the next year
    d = _valid(email_day.year, month, day)
    if d and d < email_day - timedelta(days=90):
        d = _valid(email_day.year + 1, month, day)
    return d


def resolve_event_date(raw: str, email_date_utc: str) -> str | None:
    """ISO date for a free-text event date, or None if unresolvable."""
    raw = (raw or "").strip()
    if not raw or not email_date_utc:
        return None
    try:
        email_day = date.fromisoformat(email_date_utc[:10])
    except ValueError:
        return None

    if m := _ISO_RE.search(raw):
        d = _valid(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d.isoformat() if d else None
    if m := _JP_RE.search(raw):
        d = _valid(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d.isoformat() if d else None

    d = _from_folded_text(_fold(raw), email_day)
    return d.isoformat() if d else None


def _from_folded_text(text: str, email_day: date) -> date | None:
    """Match the accent-folded date wordings, most specific pattern first."""
    if m := _NUMERIC_RE.search(text):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if month > 12 and day <= 12:  # US mm/dd/yyyy, e.g. 07/13/2026
            day, month = month, day
        return _valid(year, month, day)
    if m := _DAY_MONTH_RE.search(text):  # "18 juillet", "11th July 2026"
        return _with_inferred_year(
            _MONTH_NUM[m.group(2)], int(m.group(1)), text, email_day
        )
    if m := _MONTH_DAY_RE.search(text):  # "July 15th", "through July 9"
        return _with_inferred_year(
            _MONTH_NUM[m.group(1)], int(m.group(2)), text, email_day
        )
    if m := _NUMERIC_SHORT_RE.search(text):  # "23/06" — dd/mm, email year
        day, month = int(m.group(1)), int(m.group(2))
        if month > 12 and day <= 12:
            day, month = month, day
        return _with_inferred_year(month, day, text, email_day)
    if _AFTER_TOMORROW_RE.search(text):
        return email_day + timedelta(days=2)
    if _TOMORROW_RE.search(text):
        return email_day + timedelta(days=1)
    if _TODAY_RE.search(text):
        return email_day
    if m := _WEEKDAY_RE.search(text):  # first such day on/after the send date
        return email_day + timedelta(
            days=(_WEEKDAY_NUM[m.group(1)] - email_day.weekday()) % 7
        )
    return None


# An event or deadline more than this far before the email's send date was
# already past when the email was written (quoted history, a forwarded old
# appointment, a newsletter's past agenda); the margin absorbs time zones.
PAST_MARGIN = timedelta(days=1)
# ...or this far after it: an LLM slip (wrong year), not a real date.
FUTURE_LIMIT = timedelta(days=2 * 366)

# Unresolvable dues worth showing as written: a month or weekday name
# ("octobre", "end of August") or an urgency wording. Anything else (URLs,
# "10 minutes", "PR #95") is not a deadline and is dropped.
# Short abbreviations ("mon", "mar", "sam", "may") are left out: they are
# also everyday words ("mon compte").
_DUE_NAMES = [t for t in [*_MONTH_NUM, *_WEEKDAY_NUM] if len(t) >= 4] + ["mai"]
_DUE_WORDS_RE = re.compile(
    rf"\b({_alt(_DUE_NAMES)}|asap|as soon as possible"
    r"|des que possible|au plus vite|urgent|urgente|immediatement)\b"
)


def plausible_date(iso: str, email_date_utc: str) -> bool:
    """Whether an ISO date is not already past, nor absurdly far, at send time."""
    try:
        day = date.fromisoformat(iso)
        email_day = date.fromisoformat(email_date_utc[:10])
    except (TypeError, ValueError):
        return True  # nothing to compare against: keep it
    return email_day - PAST_MARGIN <= day <= email_day + FUTURE_LIMIT


def normalize_event_date(raw: str, email_date_utc: str) -> str | None:
    """Stored form of an event date: ISO when resolvable, else as written.

    None means the event should be dropped: its date was already past (or
    implausibly far) when the email was sent.
    """
    raw = (raw or "").strip()
    iso = resolve_event_date(raw, email_date_utc)
    if iso is None:
        return raw
    return iso if plausible_date(iso, email_date_utc) else None


def normalize_due(raw: str, email_date_utc: str) -> str:
    """Stored form of a task due: ISO date, a wording worth showing, or "".

    The time of day, when written, is not kept: the task list shows dates.
    A due already past at send time is cleared (the task itself is kept).
    """
    raw = (raw or "").strip()
    iso = resolve_event_date(raw, email_date_utc)
    if iso is not None:
        return iso if plausible_date(iso, email_date_utc) else ""
    return raw if _DUE_WORDS_RE.search(_fold(raw)) else ""


def backfill_event_dates() -> int:
    """Rewrite already-stored non-ISO event dates in place and drop events
    already past when their email was sent; returns rows changed."""
    from .db import get_conn

    changed = 0
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT ev.id, ev.date, e.date_utc FROM events ev "
            "JOIN emails e ON e.id = ev.email_id"
        ).fetchall()
        for row in rows:
            raw = row["date"] or ""
            new = normalize_event_date(raw, row["date_utc"] or "")
            if new is None:
                conn.execute("DELETE FROM events WHERE id = ?", (row["id"],))
                changed += 1
            elif new != raw:
                conn.execute(
                    "UPDATE events SET date = ? WHERE id = ?", (new, row["id"])
                )
                changed += 1
    return changed


def backfill_task_dues() -> int:
    """Normalize already-stored task dues in place; returns rows changed."""
    from .db import get_conn

    changed = 0
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT t.id, t.due, e.date_utc FROM tasks t "
            "JOIN emails e ON e.id = t.email_id"
        ).fetchall()
        for row in rows:
            raw = row["due"] or ""
            new = normalize_due(raw, row["date_utc"] or "")
            if new != raw:
                conn.execute("UPDATE tasks SET due = ? WHERE id = ?", (new, row["id"]))
                changed += 1
    return changed


if __name__ == "__main__":
    print(f"events: {backfill_event_dates()} dates resolved or dropped")
    print(f"tasks: {backfill_task_dues()} dues normalized")
