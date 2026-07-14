from datetime import datetime, timezone


from app.mail.parser import parse_date_only, parse_eml

PLAIN_EML = b"""\
From: Sarah Chen <sarah@example.com>
To: thomas@example.com
Subject: Q3 report review
Date: Fri, 10 Jul 2026 09:14:00 +0200
Message-ID: <msg-1@example.com>
Content-Type: text/plain; charset=utf-8

Hi Thomas,

can you review the report before Friday?
"""

HTML_ONLY_EML = b"""\
From: Newsletter <news@example.com>
Subject: Weekly digest
Date: Thu, 09 Jul 2026 08:00:00 +0000
Message-ID: <msg-2@example.com>
Content-Type: text/html; charset=utf-8

<html><head><style>p{color:red}</style></head>
<body><p>Hello <b>world</b></p><script>evil()</script><p>Second paragraph</p></body></html>
"""

QP_FRENCH_EML = b"""\
From: =?utf-8?q?R=C3=A9mi_Dupont?= <remi@example.fr>
Subject: =?utf-8?q?R=C3=A9union_pr=C3=A9vue?=
Date: Wed, 08 Jul 2026 15:30:00 +0200
Message-ID: <msg-3@example.fr>
Content-Type: text/plain; charset=utf-8
Content-Transfer-Encoding: quoted-printable

Bonjour, la r=C3=A9union est confirm=C3=A9e =C3=A0 15h.
"""

LATIN1_EML = b"""\
From: Vieux Systeme <old@example.fr>
Subject: Facture
Date: Tue, 07 Jul 2026 10:00:00 +0200
Message-ID: <msg-4@example.fr>
Content-Type: text/plain; charset=iso-8859-1
Content-Transfer-Encoding: 8bit

Voici la facture d'\xe9lectricit\xe9.
"""

MULTIPART_EML = b"""\
From: Multi Part <multi@example.com>
Subject: Both parts
Date: Mon, 06 Jul 2026 12:00:00 +0000
Message-ID: <msg-5@example.com>
Content-Type: multipart/alternative; boundary="B"

--B
Content-Type: text/plain; charset=utf-8

plain text version
--B
Content-Type: text/html; charset=utf-8

<p>html version</p>
--B--
"""

NO_DATE_EML = b"""\
From: nobody@example.com
Subject: no date here
Message-ID: <msg-6@example.com>

body
"""

THREAD_EML = b"""\
From: Alex <alex@example.com>
Subject: Re: thread
Date: Sun, 05 Jul 2026 09:00:00 +0000
Message-ID: <msg-7@example.com>
In-Reply-To: <msg-1@example.com>
References: <msg-0@example.com> <msg-1@example.com>

reply body
"""


def write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return p


class TestParseEml:
    def test_plain_text(self, tmp_path):
        e = parse_eml(write(tmp_path, "a.eml", PLAIN_EML))
        assert e["sender"] == "Sarah Chen"
        assert e["sender_email"] == "sarah@example.com"
        assert e["subject"] == "Q3 report review"
        assert e["message_id"] == "<msg-1@example.com>"
        assert "review the report" in e["body"]
        # Date normalized to UTC (09:14 +0200 -> 07:14Z)
        assert e["date_utc"].startswith("2026-07-10T07:14:00")

    def test_html_only_falls_back_to_text(self, tmp_path):
        e = parse_eml(write(tmp_path, "b.eml", HTML_ONLY_EML))
        assert "Hello" in e["body"] and "world" in e["body"]
        assert "Second paragraph" in e["body"]
        # script/style stripped
        assert "evil" not in e["body"]
        assert "color:red" not in e["body"]

    def test_quoted_printable_french(self, tmp_path):
        e = parse_eml(write(tmp_path, "c.eml", QP_FRENCH_EML))
        assert e["sender"] == "Rémi Dupont"
        assert e["subject"] == "Réunion prévue"
        assert "réunion est confirmée à 15h" in e["body"]

    def test_latin1_charset(self, tmp_path):
        e = parse_eml(write(tmp_path, "d.eml", LATIN1_EML))
        assert "électricité" in e["body"]

    def test_multipart_prefers_plain(self, tmp_path):
        e = parse_eml(write(tmp_path, "e.eml", MULTIPART_EML))
        assert e["body"] == "plain text version"

    def test_missing_date_returns_none(self, tmp_path):
        assert parse_eml(write(tmp_path, "f.eml", NO_DATE_EML)) is None

    def test_thread_headers(self, tmp_path):
        e = parse_eml(write(tmp_path, "g.eml", THREAD_EML))
        assert e["in_reply_to"] == "<msg-1@example.com>"
        assert "<msg-0@example.com>" in e["refs"]

    def test_missing_subject_and_sender_defaults(self, tmp_path):
        raw = b"Date: Mon, 06 Jul 2026 12:00:00 +0000\n\nbody\n"
        e = parse_eml(write(tmp_path, "h.eml", raw))
        assert e["subject"] == "(no subject)"
        assert e["sender"] == "(unknown)"

    def test_snippet_and_body_truncation(self, tmp_path):
        raw = (
            b"From: a@b.c\nSubject: big\nDate: Mon, 06 Jul 2026 12:00:00 +0000\n\n"
            + b"x" * 50000
        )
        e = parse_eml(write(tmp_path, "i.eml", raw))
        assert len(e["snippet"]) == 300
        assert len(e["body"]) == 20000


class TestUnread:
    def _base(self, extra_headers=b"", name="m.eml"):
        return (
            b"From: a@b.c\nSubject: s\nDate: Mon, 06 Jul 2026 12:00:00 +0000\n"
            + extra_headers
            + b"\nbody\n"
        ), name

    def test_mozilla_status_read(self, tmp_path):
        raw, name = self._base(b"X-Mozilla-Status: 0001\n")
        assert parse_eml(write(tmp_path, name, raw))["unread"] is False

    def test_mozilla_status_unread(self, tmp_path):
        raw, name = self._base(b"X-Mozilla-Status: 0000\n")
        assert parse_eml(write(tmp_path, name, raw))["unread"] is True

    def test_maildir_flag_seen(self, tmp_path):
        raw, _ = self._base()
        assert parse_eml(write(tmp_path, "m.eml:2,S", raw))["unread"] is False

    def test_maildir_flag_not_seen(self, tmp_path):
        raw, _ = self._base()
        assert parse_eml(write(tmp_path, "m.eml:2,", raw))["unread"] is True

    def test_no_flags_defaults_to_read(self, tmp_path):
        raw, name = self._base()
        assert parse_eml(write(tmp_path, name, raw))["unread"] is False


class TestParseDateOnly:
    def test_reads_date_from_header_block(self, tmp_path):
        p = write(tmp_path, "a.eml", PLAIN_EML)
        dt = parse_date_only(p)
        assert dt == datetime(2026, 7, 10, 7, 14, tzinfo=timezone.utc)

    def test_missing_date(self, tmp_path):
        assert parse_date_only(write(tmp_path, "f.eml", NO_DATE_EML)) is None

    def test_naive_date_assumed_utc(self, tmp_path):
        raw = b"Date: Mon, 06 Jul 2026 12:00:00 -0000\n\nbody\n"
        dt = parse_date_only(write(tmp_path, "n.eml", raw))
        assert dt.tzinfo is not None
        assert dt.hour == 12
