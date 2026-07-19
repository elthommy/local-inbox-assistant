from app.mail.render import MAX_MARKDOWN_CHARS, render_email

HTML_EML = b"""\
From: Newsletter <news@example.com>
Subject: Weekly digest
Date: Thu, 09 Jul 2026 08:00:00 +0000
Message-ID: <msg-html@example.com>
Content-Type: text/html; charset=utf-8

<html><head><title>digest</title><style>p{color:red}</style></head>
<body>
<h1>This week</h1>
<p>Hello <b>world</b>, read <a href="https://example.com/post">the post</a>.</p>
<img src="https://tracker.example.com/pixel.gif" alt="pixel">
<script>evil()</script>
<ul><li>one</li><li>two</li></ul>
</body></html>
"""

MULTIPART_EML = b"""\
From: Multi Part <multi@example.com>
Subject: Both parts
Date: Mon, 06 Jul 2026 12:00:00 +0000
Message-ID: <msg-multi@example.com>
Content-Type: multipart/alternative; boundary="B"

--B
Content-Type: text/plain; charset=utf-8

plain text version
--B
Content-Type: text/html; charset=utf-8

<p>html <em>version</em></p>
--B--
"""

PLAIN_EML = b"""\
From: Sarah Chen <sarah@example.com>
Subject: Q3 report review
Date: Fri, 10 Jul 2026 09:14:00 +0200
Message-ID: <msg-plain@example.com>
Content-Type: text/plain; charset=utf-8

just plain text here
"""


def html_eml(body_html: bytes) -> bytes:
    """Wrap an HTML body in minimal .eml headers."""
    return (
        b"From: a@b.c\nSubject: s\nDate: Mon, 06 Jul 2026 12:00:00 +0000\n"
        b"Content-Type: text/html; charset=utf-8\n\n" + body_html
    )


# wall of tracking links with barely any text: trips link density
LINK_WALL = html_eml(
    b"<p>"
    + b"".join(
        b'<a href="https://t.example.com/click?cid=%d&tok=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa">Shop</a> '
        % i
        for i in range(10)
    )
    + b"</p>"
)

# layout table converted verbatim to pipe rows: trips table-line fraction
TABLE_LAYOUT = html_eml(
    b"<table>"
    + b"".join(b"<tr><td>cell</td><td>cell</td></tr>" for _ in range(10))
    + b"</table>"
)

# almost no visible text but lots of markup output: trips markup overhead
RULE_SOUP = html_eml(b"<p>hi</p>" + b"<hr>" * 40)


def write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return p


class TestRenderEmail:
    def test_converts_html_to_markdown(self, tmp_path):
        r = render_email(write(tmp_path, "a.eml", HTML_EML))
        assert r is not None
        assert "# This week" in r.markdown
        assert "**world**" in r.markdown
        assert "[the post](https://example.com/post)" in r.markdown
        assert "* one" in r.markdown and "* two" in r.markdown

    def test_strips_images_scripts_and_styles(self, tmp_path):
        r = render_email(write(tmp_path, "a.eml", HTML_EML))
        assert r is not None
        assert "pixel" not in r.markdown
        assert "tracker.example.com" not in r.markdown
        assert "evil" not in r.markdown
        assert "color:red" not in r.markdown
        assert "digest" not in r.markdown  # <title> dropped

    def test_uses_html_part_of_multipart(self, tmp_path):
        r = render_email(write(tmp_path, "m.eml", MULTIPART_EML))
        assert r is not None
        assert "html *version*" in r.markdown
        assert "plain text version" not in r.markdown

    def test_plain_text_email_returns_none(self, tmp_path):
        assert render_email(write(tmp_path, "p.eml", PLAIN_EML)) is None

    def test_missing_file_returns_none(self, tmp_path):
        assert render_email(tmp_path / "gone.eml") is None

    def test_output_is_capped(self, tmp_path):
        raw = html_eml(b"<p>" + b"x" * (MAX_MARKDOWN_CHARS * 2) + b"</p>")
        r = render_email(write(tmp_path, "big.eml", raw))
        assert r is not None
        assert len(r.markdown) == MAX_MARKDOWN_CHARS


class TestDegradation:
    def test_clean_email_is_not_degraded(self, tmp_path):
        r = render_email(write(tmp_path, "a.eml", HTML_EML))
        assert r is not None
        assert r.degraded is False

    def test_link_wall_is_degraded(self, tmp_path):
        r = render_email(write(tmp_path, "l.eml", LINK_WALL))
        assert r is not None
        assert r.degraded is True

    def test_layout_table_is_degraded(self, tmp_path):
        r = render_email(write(tmp_path, "t.eml", TABLE_LAYOUT))
        assert r is not None
        assert r.degraded is True

    def test_markup_overhead_is_degraded(self, tmp_path):
        r = render_email(write(tmp_path, "h.eml", RULE_SOUP))
        assert r is not None
        assert r.degraded is True
