# Roadmap & status

Living status of the project, so work survives interrupted sessions. **Every
session (human or agent) reads this first and updates it** when an item
starts, changes direction, or finishes. Newest information wins; move
finished items to "Done" with the PR number.

This repo is public: keep this file free of personal data (no names,
senders, addresses or mail content from a real mailbox). Local-only
artifacts live under `backend/data/` (git-ignored).

## In progress

**"My priorities" sender pre-filter** (branch `feat/priorities-prefilter`).
Appending every rule to every parsing prompt shifted ~1% of unrelated
emails' priority (benchmark: 2 wrong, 3 right out of 280). Now
`app/my_priorities.py` splits the text into rules (one per line) and adds a
rule to an email's prompt only when it names the sender: a word of the
display name, of the organisation domain (`caz.bank.fr` → `bank`), or of the
address local part at a personal provider (Gmail, Outlook…). Generic words
("notifications", "club", "statements", "votre"…) never select a rule.
Emails no rule names get exactly the default prompt, so their result cannot
move; no GPU benchmark needed for them. On the real mailbox the live rule now
reaches only its own organisation's 69 emails (all 4 known vote emails
included); a first word-based version reached 186 (quoted subject words like
"action", "votre" matched banks and utilities). UI hint and README say "one
rule per line, naming the sender".

Left: open the PR. Optional, needs the GPU (~20 min): re-parse the stored
emails so results parsed with all rules on 2026-11-10 lose the side effect.

## Next

Nothing queued; pick from "Later / ideas".

## Later / ideas

- Remaining extraction weaknesses after v4.1 (fresh holdout): a few
  account-change notices still rated medium, a few invented events from
  promotional deadlines; important-mail recall ~3–5 of 5 per 50-email set.
- mbox support — deferred until requested (see README "Limitation").

## Done

- 2026-11-11 — #61 dates and thread dedup + extraction prompt **v6**: tasks
  and events listed once per (thread, date) (`app/threads.py`, read-time
  only); task dues normalized like event dates, past or far-future dates
  dropped, backfill command `python -m app.event_dates`; v6 drops public /
  mailing-list announcements and public notices from events (invented events
  4 → 2 on 280 hand-checked emails). Real DB: listed tasks 80 → 44, events
  80 → 29.

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
