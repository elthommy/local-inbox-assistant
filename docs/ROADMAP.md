# Roadmap & status

Living status of the project, so work survives interrupted sessions. **Every
session (human or agent) reads this first and updates it** when an item
starts, changes direction, or finishes. Newest information wins; move
finished items to "Done" with the PR number.

This repo is public: keep this file free of personal data (no names,
senders, addresses or mail content from a real mailbox). Local-only
artifacts live under `backend/data/` (git-ignored).

## In progress

**Dates and thread dedup** (branch `feat/dates-thread-dedup`, not yet
committed). Done, no GPU used:
- `app/threads.py`: emails grouped by thread (Message-ID / In-Reply-To /
  References, union-find); `/api/tasks`, `/api/events`, the chat context and
  the MCP tools list a task/event once per (thread, date), the newest
  email's copy winning. Read-time only, nothing deleted. Collapsing by date
  rather than "newest email only" because a later reply can mention a
  different appointment (someone else's) that must not hide the first.
- `app/event_dates.py`: `31-JUL-2026` / `21-07-2026` forms; task dues
  normalized like event dates (ISO; month-only or urgency wordings kept as
  written; URLs, durations and other non-dates cleared); events and dues
  already past at the email's send date (or > 2 years ahead) dropped.
  `python -m app.event_dates` backfills stored rows. The UI shows dues in
  the chosen date format.
- Backfill applied to the real DB on 2026-11-02 (backup taken first in
  `backend/data/`, git-ignored): 10 events fixed or dropped, 37 dues
  normalized; listed tasks 80 → 69, events 80 → 65.

- Extraction prompt **v6** (2026-11-10): events announced to a mailing list
  or the public (venue/shop/association agendas, product launches, earnings
  announcements, crowdfunding openings) and public notices about roads,
  public works or outages are not events; 2 examples added. Benchmark on
  the 280 hand-checked emails: invented events 4 → 2, real events found
  unchanged (18/20), priority accuracy equal or better on every set. Of the
  83 emails that had a stored event, 42 keep one (all road-closure and
  crowdfunding mail dropped). All 904 parsed emails re-parsed with v6 on
  2026-11-10 (DB backup taken first in `backend/data/`, git-ignored):
  listed tasks 69 → 44, events 65 → 29; 83 emails medium → low, mostly
  older results now following the v5 rules (forge/forum notifications,
  bank alerts, account notices). A few changes to spot-check in the UI.

Left: commit and open the PR.

## Next

1. **"My priorities" side effect.** Appending any rule shifts ~1% of
   unrelated emails' priority (benchmark: 2 wrong, 3 right out of 280).
   A per-rule pre-filter (match the sender before adding the rule) would
   remove that.

## Later / ideas

- Remaining extraction weaknesses after v4.1 (fresh holdout): a few
  account-change notices still rated medium, a few invented events from
  promotional deadlines; important-mail recall ~3–5 of 5 per 50-email set.
- mbox support — deferred until requested (see README "Limitation").

## Done

- 2026-11-02 — #57 multilingual retrieval: `scripts.benchmark_retrieval` (demo
  mailbox + 1 000 real emails as distractors, does the answering email reach
  the chat's top 6). Default embedding model `nomic-embed-text` →
  `embeddinggemma`: 9/16 → 15/16 questions, cross-language 5/12 → 11/12.
  Per-model query/document prefixes (`EMBED_PREFIXES`); the index records its
  embedding setup and rebuilds itself once when it changes (~3 min for the
  full mailbox).
- 2026-11-02 — #56 chat model choice: `scripts.benchmark_chat` (21 EN/FR
  questions ×2 on the demo mailbox, facts + answer language + speed). The
  chat prompt now names the question's language (detected in
  `app/lang.py`) at its end; `gemma4:12b` went from 36% to 93% of answers
  passing, 100% in the right language, and is the new chat default (one
  model for chat and parsing) marked "★ recommended" in both pickers.
  Runs in `backend/data/benchmark/chat-2026-11-02*/` (git-ignored).
- 2026-11-01 — priority view spot-checked after the v5 re-parse, with a
  personal rule set in "My priorities".
- 2026-11-01 — #55 demo data + launch video: 27-email synthetic corpus with
  seed-time dates, `seed_demo --skip-embed`, `scripts.demo_server` (scripted
  chat, no model), storyboard `docs/demo-scenario.md`, 20 s video in the
  README (made on Claude Web from that branch).
- 2026-11-01 — #54 extraction prompt **v5** (automated order / status / shipping
  mail low, plain delivery dates no longer events, pickups and replies
  written by people stay medium; invented events 8/4/2/7 → 2/0/0/2 on 280
  emails with 11 labels revised) and **"My priorities"** (settings drawer
  free text, local DB, changes priority only; acceptance test: every vote
  email of the target sender rises to high, its 65 other emails stay low).
  Benchmark in `backend/data/benchmark/v5-2026-11-01/` (git-ignored).
- 2026-11-01 — stored mail re-parsed with v4.1 (spot-check findings in
  "Later / ideas").
- 2026-11-01 — #52 extraction prompt v4.1 (events need a concrete date and
  a personal link; account notifications low; suggestions are not tasks;
  own sent mail flagged via Sent-folder owner detection) + this roadmap.
  `gemma4:12b` priority accuracy 0.93/0.94/0.96/0.86 on 280 hand-checked
  emails (was 0.88/0.92/0.92/0.78).
- 2026-10-31 — #51 stricter extraction prompt (v3) + `gemma4:12b` default
  parsing model, benchmarked on 230 hand-checked emails.
- 2026-10-31 — #48/#49/#50 auto-pull of missing Ollama models + download
  prompt (`INBOX_AUTO_PULL=ask|always|never`).
- 2026-10-31 — #47 CodeQL fixes + security hardening (DNS rebinding, CSRF,
  chat image exfiltration); security model in `AGENTS.md`.
