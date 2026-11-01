# Roadmap & status

Living status of the project, so work survives interrupted sessions. **Every
session (human or agent) reads this first and updates it** when an item
starts, changes direction, or finishes. Newest information wins; move
finished items to "Done" with the PR number.

This repo is public: keep this file free of personal data (no names,
senders, addresses or mail content from a real mailbox). Local-only
artifacts live under `backend/data/` (git-ignored).

## In progress

Nothing running. App is up (`./start.sh`), no Ollama model loaded.

## Next

1. **"My priorities" — personal triage rules.** A free-text box in the
   settings drawer (e.g. "votes on my crowdfunding investments are high
   priority; their promotions stay low"), stored in the local DB like the
   model choice and appended to the extraction prompt. Private by design:
   never in code or the repo. Acceptance test on the local benchmark set
   (`backend/data/benchmark/gold-2026-10-31/`): the rule promotes the
   intended kind of email without promoting promotions from the same
   sender, and does not change other labels. Follow AGENTS.md
   "Long-running GPU jobs" for any GPU run.

## Later / ideas

- Evaluate the **chat** model choice (`gemma4:12b` was only evaluated for
  extraction; `qwen3:8b` drifts into the mailbox's language).
- Remaining extraction weaknesses after v4.1 (fresh holdout): a few
  account-change notices still rated medium, a few invented events from
  promotional deadlines; important-mail recall ~3–5 of 5 per 50-email set.
- Spot-check after the v4.1 re-parse (2026-11-01, 267 emails of the last
  14 days: 1 high, 46 medium, 220 low):
  - medium is padded with routine order / pick-up / repair-status mail;
  - deliveries and road-closure notices become events, and a shop
    newsletter's agenda still yields several events per email;
  - dates are not normalised (`06-NOV-2026`, free-text task due dates), and
    one shareholder-meeting event got an implausible date;
  - one reply thread yields the same task/event once per message (no
    dedup across a thread).
- mbox support — deferred until requested (see README "Limitation").

## Done

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
