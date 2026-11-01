# Roadmap & status

Living status of the project, so work survives interrupted sessions. **Every
session (human or agent) reads this first and updates it** when an item
starts, changes direction, or finishes. Newest information wins; move
finished items to "Done" with the PR number.

This repo is public: keep this file free of personal data (no names,
senders, addresses or mail content from a real mailbox). Local-only
artifacts live under `backend/data/` (git-ignored).

## In progress

- **Demo data for the launch video** (branch `demo-video-data`, not merged):
  27-email corpus with seed-time dates, `seed_demo --skip-embed`,
  `scripts.demo_server` (scripted chat, no model), storyboard in
  `docs/demo-scenario.md`, frames in `docs/demo-screens/`; launch video
  (made on Claude Web) in `docs/media/demo.mp4`, linked from the README.
  Next: review / merge.

## Next

1. **Review / merge #54** (prompt v5 + "My priorities").
2. Spot-check the priority view after the v5 re-parse (done 2026-11-01 with a
   personal rule set in "My priorities").

## Later / ideas

- Evaluate the **chat** model choice (`gemma4:12b` was only evaluated for
  extraction; `qwen3:8b` drifts into the mailbox's language).
- Remaining extraction weaknesses after v4.1 (fresh holdout): a few
  account-change notices still rated medium, a few invented events from
  promotional deadlines; important-mail recall ~3–5 of 5 per 50-email set.
- Left over from the v4.1 spot-check (2026-11-01): event/task dates are not
  normalised (`06-NOV-2026`, free-text due dates; one implausible
  shareholder-meeting date); a reply thread yields the same task/event once
  per message (no dedup across a thread); a shop newsletter's agenda and
  road-closure notices still become events.
- "My priorities" side effects: appending any rule shifts ~1% of unrelated
  emails' priority (benchmark: 2 wrong, 3 right out of 280). A per-rule
  pre-filter (match sender before adding the rule) would remove that.
- mbox support — deferred until requested (see README "Limitation").

## Done

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
