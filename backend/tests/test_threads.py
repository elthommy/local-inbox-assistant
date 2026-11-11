"""Reply-thread grouping and the collapse of tasks/events repeated in it."""

from app.db import get_conn
from app.threads import collapse_rows, collapse_thread_duplicates, thread_keys


def add_email(conn, n, *, msgid="", reply_to="", refs="", day="2026-10-01"):
    """Insert email number n with the given threading headers; returns its id."""
    cur = conn.execute(
        "INSERT INTO emails(maildir_file, message_id, in_reply_to, refs, date_utc) "
        "VALUES(?, ?, ?, ?, ?)",
        (f"{n}.eml", msgid, reply_to, refs, f"{day}T10:00:{n:02d}+00:00"),
    )
    return cur.lastrowid


class TestThreadKeys:
    def test_links_through_reply_to_and_references(self):
        with get_conn() as conn:
            root = add_email(conn, 1, msgid="<r@x>")
            reply = add_email(conn, 2, msgid="<b@x>", reply_to="<r@x>")
            # no References, only In-Reply-To to the reply: still the thread
            deep = add_email(conn, 3, msgid="<c@x>", reply_to="<b@x>")
            via_refs = add_email(conn, 4, msgid="<d@x>", refs="<r@x> <b@x>")
            other = add_email(conn, 5, msgid="<o@x>")
            keys = thread_keys(conn)
        assert keys[root] == keys[reply] == keys[deep] == keys[via_refs]
        assert keys[other] != keys[root]

    def test_reply_seen_before_its_root_and_missing_message_id(self):
        with get_conn() as conn:
            reply = add_email(conn, 1, msgid="<b@x>", refs="<r@x>")
            root = add_email(conn, 2, msgid="<r@x>")
            lone_a = add_email(conn, 3)
            lone_b = add_email(conn, 4)
            keys = thread_keys(conn)
        assert keys[reply] == keys[root]
        assert keys[lone_a] != keys[lone_b]  # no id: never merged

    def test_comment_after_in_reply_to_is_ignored(self):
        with get_conn() as conn:
            root = add_email(conn, 1, msgid="<r@x>")
            reply = add_email(
                conn, 2, msgid="<b@x>", reply_to="<r@x> (Jane's message of Mon)"
            )
            keys = thread_keys(conn)
        assert keys[root] == keys[reply]


def row(email_id, date, day="2026-10-01", text=""):
    """A task/event-like row as the listing queries return it."""
    return {"email_id": email_id, "date": date, "date_utc": day, "text": text}


class TestCollapse:
    KEYS = {1: "t", 2: "t", 3: "t", 9: "other"}

    def test_same_date_in_a_thread_keeps_the_newest_copy(self):
        rows = [
            row(1, "2026-11-06", "2026-10-20"),
            row(2, "2026-11-06", "2026-10-22"),
            row(9, "2026-11-06", "2026-10-21"),  # other thread: kept
        ]
        kept = collapse_thread_duplicates(rows, self.KEYS, "date")
        assert [r["email_id"] for r in kept] == [2, 9]

    def test_different_dates_in_a_thread_are_distinct_items(self):
        # a later reply mentioning another appointment must not hide the first
        rows = [row(1, "2026-11-06", "2026-10-20"), row(3, "2026-11-09", "2026-10-22")]
        assert collapse_thread_duplicates(rows, self.KEYS, "date") == rows

    def test_several_items_of_the_newest_email_all_stay(self):
        rows = [
            row(1, "", "2026-10-20", "confirm availability"),
            row(2, "", "2026-10-22", "send remarks"),
            row(2, "", "2026-10-22", "pick a representative"),
        ]
        kept = collapse_thread_duplicates(rows, self.KEYS, "date")
        assert [r["text"] for r in kept] == ["send remarks", "pick a representative"]

    def test_unknown_email_is_its_own_thread(self):
        rows = [row(7, "2026-11-06"), row(8, "2026-11-06")]
        assert collapse_thread_duplicates(rows, {}, "date") == rows

    def test_collapse_rows_empty(self):
        with get_conn() as conn:
            assert collapse_rows(conn, [], "date") == []
