"""Capture the docs/demo-scenario.md storyboard states from the real UI.

Needs the demo stack running (see docs/demo-scenario.md) and a Chromium.
Playwright is not a project dependency; run it ad hoc from backend/:

    uv run --with playwright python -m scripts.capture_demo_screens \
        ../docs/demo-screens --url http://localhost:5173/ --chromium /usr/bin/chromium

The browser clock is set to 08:50 today (the seed's story time) and the locale
to en-GB, so chat timestamps and dates match the seeded mailbox.
"""

import argparse
import re
from datetime import datetime

from playwright.sync_api import sync_playwright


def ask(pg, text, wait=4500):
    """Type a question in the chat input and wait for the scripted stream."""
    box = pg.get_by_placeholder("Ask about your inbox…")
    box.fill(text)
    box.press("Enter")
    pg.wait_for_timeout(wait)


def tab(pg, label):
    """Click a list tab by its label prefix."""
    pg.get_by_text(label, exact=False).first.click()
    pg.wait_for_timeout(1000)


def capture(out: str, url: str, chromium: str | None) -> None:
    """Walk the storyboard and save one 1920x1080 PNG per state into `out`."""
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=chromium)
        ctx = b.new_context(viewport={"width": 1920, "height": 1080}, locale="en-GB")
        pg = ctx.new_page()
        pg.clock.install(time=datetime.now().replace(hour=8, minute=50, second=0))
        pg.goto(url)
        pg.wait_for_timeout(2500)
        _walk(pg, out)
        b.close()


def _walk(pg, out: str) -> None:
    """Drive the UI through each storyboard beat, screenshotting each one."""
    pg.screenshot(path=f"{out}/01_priority.png")
    pg.get_by_text("[SEV-1] checkout-api: 5xx rate at 18%", exact=True).first.click()
    pg.wait_for_timeout(1200)
    pg.screenshot(path=f"{out}/02_incident_open.png")
    ask(pg, "What needs my attention today?")
    pg.screenshot(path=f"{out}/03_attention_today.png")
    ask(pg, "Qu'est-ce que je dois faire pour l'AG de copropriété ?")
    pg.screenshot(path=f"{out}/04_ag_french.png")
    tab(pg, "tasks (")
    pg.screenshot(path=f"{out}/05_tasks.png")
    tab(pg, "events (")
    pg.screenshot(path=f"{out}/06_events.png")
    ask(pg, "Any events this week?")
    pg.screenshot(path=f"{out}/07_events_chat.png")
    pg.reload()
    pg.wait_for_timeout(2500)
    tab(pg, "all mail (")
    pg.screenshot(path=f"{out}/08_all_mail.png")
    pg.get_by_text(re.compile(r"^Convocation à l'assemblée")).first.click()
    pg.wait_for_timeout(1200)
    pg.get_by_text("≡ summarize").first.click()
    pg.wait_for_timeout(5000)
    pg.screenshot(path=f"{out}/09_summarize_fr.png")


def main() -> None:
    """Parse arguments and capture the screenshots."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", help="directory for the PNG files")
    parser.add_argument("--url", default="http://localhost:5173/")
    parser.add_argument("--chromium", help="Chromium binary (default: Playwright's)")
    args = parser.parse_args()
    capture(args.out, args.url, args.chromium)


if __name__ == "__main__":
    main()
