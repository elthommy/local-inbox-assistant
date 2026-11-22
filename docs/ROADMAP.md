# Roadmap & status

Living status of the project, so work survives interrupted sessions. **Every
session (human or agent) reads this first and updates it** when an item
starts, changes direction, or finishes. Newest information wins; move
finished items to "Done" with the PR number.

This repo is public: keep this file free of personal data (no names,
senders, addresses or mail content from a real mailbox). Local-only
artifacts live under `backend/data/` (git-ignored).

## In progress

Nothing in progress.

## Next

Nothing queued; pick from "Later / ideas".

## Later / ideas

- Remaining extraction weaknesses after v4.1 (fresh holdout): a few
  account-change notices still rated medium, a few invented events from
  promotional deadlines; important-mail recall ~3–5 of 5 per 50-email set.
- Optional, needs the GPU (~20 min): re-parse the stored emails so results
  parsed with every "My priorities" rule on 2026-11-10 lose the side effect
  fixed by #62.
- mbox support — deferred until requested (see README "Limitation").
- Hybrid keyword + vector retrieval (SQLite FTS5 + rank fusion) — **decided
  not to do for now (2026-11-22): too complex for the gain.** Vector-only
  embeddinggemma already ranks every reference-number lookup 1st, even among
  20 near-identical copies (cosine gap +0.04 to +0.14). FTS5 could only fix 2
  of 26 benchmark questions: a name in a cross-language question (`priya`,
  rank 255) and "résolution n°7" (rank 9). Revisit if name lookups across
  languages become a real complaint; the lookup benchmark is ready to measure it.

## Done

- 2026-11-22 — #70 retrieval lookup benchmark: `scripts.benchmark_retrieval`
  gains 10 `LOOKUP_QUESTIONS` (own column), `--near-dups N` and `--only`.
  embeddinggemma (vector only): chat 15/16, lookup 9/10, reference lookups
  still 1st among 20 near-identical copies. Hybrid FTS5 shelved (see
  "Later / ideas").
- 2026-11-11 — #62 "My priorities" sender pre-filter: a rule (one per line)
  is added to an email's parsing prompt only when it names the sender
  (display name, organisation domain, or local part at a personal
  provider); generic words never select a rule, and emails no rule names
  get exactly the default prompt. On the real mailbox the live rule reaches
  only its own organisation's emails.
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
