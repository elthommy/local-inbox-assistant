# Roadmap & status

Living status of the project, so work survives interrupted sessions. **Every
session (human or agent) reads this first and updates it** when an item
starts, changes direction, or finishes. Newest information wins; move
finished items to "Done" with the PR number.

This repo is public: keep this file free of personal data (no names,
senders, addresses or mail content from a real mailbox). Local-only
artifacts live under `backend/data/` (git-ignored).

## In progress

Nothing running.

## Next

1. **Dates and thread dedup.** Normalise event/task dates (`06-NOV-2026`,
   free-text due dates, implausible dates); one task/event per reply thread
   instead of one per message; a shop newsletter's agenda and road-closure
   notices should not become events.
2. **"My priorities" side effect.** Appending any rule shifts ~1% of
   unrelated emails' priority (benchmark: 2 wrong, 3 right out of 280).
   A per-rule pre-filter (match the sender before adding the rule) would
   remove that.

## Later / ideas

- Remaining extraction weaknesses after v4.1 (fresh holdout): a few
  account-change notices still rated medium, a few invented events from
  promotional deadlines; important-mail recall ~3–5 of 5 per 50-email set.
- Cross-language retrieval: an English question about a French email can
  miss it ("Was my parcel delivered?" never retrieves "Votre colis a été
  livré"), with every chat model (2026-11-02 chat benchmark). A multilingual
  embedding model, or translating the query, would fix it; changing the
  embedding model means rebuilding the index.
- mbox support — deferred until requested (see README "Limitation").

## Done

- 2026-11-02 — chat model choice: `scripts.benchmark_chat` (21 EN/FR
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
