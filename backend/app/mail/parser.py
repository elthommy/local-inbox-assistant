"""Parse a Thunderbird maildir .eml file into a flat dict.

Uses only the stdlib `email` package (policy.default handles RFC 2047 header
decoding and charset detection) plus BeautifulSoup for HTML->text fallback.
"""

from __future__ import annotations

import email
import email.message
import email.policy
import email.utils
import re
from datetime import UTC, datetime
from pathlib import Path

from bs4 import BeautifulSoup

# X-Mozilla-Status flag bit: message has been read
_MOZILLA_READ = 0x0001

_WS_RE = re.compile(r"[ \t\x0b\f\r]+")
_NL_RE = re.compile(r"\n{3,}")


def _clean_text(text: str) -> str:
    """Collapse runs of whitespace and blank lines, trim each line."""
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _NL_RE.sub("\n\n", text)
    return text.strip()


def _html_to_text(html: str) -> str:
    """Extract visible text from an HTML body (scripts/styles dropped)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    return soup.get_text(separator="\n")


def _best_body(msg: email.message.EmailMessage) -> str:
    """Best-effort text body: text/plain part first, then converted HTML."""
    plain = msg.get_body(preferencelist=("plain",))
    if plain is not None:
        try:
            return _clean_text(plain.get_content())
        except Exception:
            pass
    html = msg.get_body(preferencelist=("html",))
    if html is not None:
        try:
            return _clean_text(_html_to_text(html.get_content()))
        except Exception:
            pass
    return ""


def _parse_unread(msg: email.message.EmailMessage, path: Path) -> bool:
    """Unread state from X-Mozilla-Status, falling back to maildir filename flags."""
    status = msg.get("X-Mozilla-Status")
    if status:
        try:
            return not (int(status.strip(), 16) & _MOZILLA_READ)
        except ValueError:
            pass
    # maildir filename flags: ...:2,S means seen
    name = path.name
    if ":2," in name:
        return "S" not in name.rsplit(":2,", 1)[1]
    return False


def parse_eml(path: Path) -> dict | None:
    """Parse one .eml file. Returns None if the file has no usable Date."""
    with open(path, "rb") as f:
        msg = email.message_from_binary_file(f, policy=email.policy.default)

    date_hdr = msg.get("Date")
    dt = None
    if date_hdr:
        try:
            dt = email.utils.parsedate_to_datetime(str(date_hdr))
        except (ValueError, TypeError):
            dt = None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(UTC)

    sender_name, sender_email = email.utils.parseaddr(str(msg.get("From", "")))
    body = _best_body(msg)

    return {
        "maildir_file": path.name,
        "message_id": (msg.get("Message-ID") or "").strip(),
        "sender": sender_name or sender_email or "(unknown)",
        "sender_email": sender_email,
        "subject": str(msg.get("Subject", "")).strip() or "(no subject)",
        "date_utc": dt.isoformat(),
        "unread": _parse_unread(msg, path),
        "snippet": body[:300],
        "body": body[:20000],
        "in_reply_to": (msg.get("In-Reply-To") or "").strip(),
        "refs": (msg.get("References") or "").strip(),
    }


def parse_date_only(path: Path) -> datetime | None:
    """Cheap date probe: read only the header block."""
    header_bytes = b""
    with open(path, "rb") as f:
        for line in f:
            if line in (b"\n", b"\r\n"):
                break
            header_bytes += line
            if len(header_bytes) > 32768:
                break
    msg = email.message_from_bytes(header_bytes, policy=email.policy.default)
    date_hdr = msg.get("Date")
    if not date_hdr:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(str(date_hdr))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
