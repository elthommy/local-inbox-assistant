"""Render an email's HTML part as simple Markdown for on-screen reading.

The DB only stores extracted plain text; this re-opens the source .eml on
demand, so it works for already-indexed mail without a re-index.

Degradation heuristic
---------------------
Marketing-style emails built from nested layout tables degrade into walls
of tracking links and pipe tables when converted to Markdown. Rather than
guessing from sender headers (bulk mail can render fine), the converted
OUTPUT is scored, and the rendering is flagged "degraded" when any of
these signals trips:

- link density > LINK_DENSITY_MAX — fraction of the markdown occupied by
  ``[text](url)`` constructs; bad conversions are dominated by tracking URLs
- markup overhead > MARKUP_OVERHEAD_MAX — markdown length divided by the
  visible-text length of the HTML; clean conversions stay near 1x, table
  soup balloons well past it
- table lines > TABLE_LINE_FRACTION_MAX — fraction of non-empty lines that
  are ``|`` table rows, i.e. layout tables converted verbatim

For degraded emails the API falls back to the stored plain text and sets
``degraded: true`` so the UI can flag it and offer a "render anyway"
override (``?force_markdown=true``). Scores are logged per conversion so
the thresholds can be tuned against a real mailbox.
"""

from __future__ import annotations

import email
import email.policy
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify

log = logging.getLogger(__name__)

# keeps a multi-MB newsletter from flooding the API response and the UI
MAX_MARKDOWN_CHARS = 30_000

# degradation thresholds (see module docstring)
LINK_DENSITY_MAX = 0.5
MARKUP_OVERHEAD_MAX = 2.5
TABLE_LINE_FRACTION_MAX = 0.3

_NL_RE = re.compile(r"\n{3,}")
_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")


@dataclass(frozen=True)
class RenderedEmail:
    """A Markdown rendering plus the degradation verdict on its quality."""

    markdown: str
    degraded: bool


def _html_part(path: Path) -> str | None:
    """Decoded HTML body part of an .eml file, or None if absent/unreadable."""
    try:
        with open(path, "rb") as f:
            msg = email.message_from_binary_file(f, policy=email.policy.default)
        part = msg.get_body(preferencelist=("html",))
        return part.get_content() if part is not None else None
    except Exception:
        log.warning("could not read HTML part of %s", path, exc_info=True)
        return None


def _looks_degraded(md: str, visible_len: int) -> bool:
    """Score a conversion; True when Markdown noise drowns the content."""
    link_chars = sum(len(m) for m in _LINK_RE.findall(md))
    link_density = link_chars / max(len(md), 1)
    overhead = len(md) / max(visible_len, 1)
    lines = [ln for ln in md.splitlines() if ln.strip()]
    table_fraction = sum(1 for ln in lines if ln.lstrip().startswith("|")) / max(
        len(lines), 1
    )
    degraded = (
        link_density > LINK_DENSITY_MAX
        or overhead > MARKUP_OVERHEAD_MAX
        or table_fraction > TABLE_LINE_FRACTION_MAX
    )
    log.info(
        "render quality: link_density=%.2f overhead=%.2f table_fraction=%.2f -> %s",
        link_density,
        overhead,
        table_fraction,
        "degraded" if degraded else "ok",
    )
    return degraded


def render_email(path: Path) -> RenderedEmail | None:
    """Markdown rendering of the email's HTML part; None when unavailable.

    Images are stripped (loading them would leak tracking pixels); script,
    style and head content never reaches the output. ``degraded`` is the
    verdict of the heuristic documented in the module docstring.
    """
    html = _html_part(path)
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head", "title"]):
        tag.decompose()
    visible_len = len(" ".join(soup.get_text().split()))
    md = markdownify(str(soup), strip=["img"], heading_style="ATX")
    md = _NL_RE.sub("\n\n", md).strip()[:MAX_MARKDOWN_CHARS]
    if not md:
        return None
    return RenderedEmail(markdown=md, degraded=_looks_degraded(md, visible_len))
