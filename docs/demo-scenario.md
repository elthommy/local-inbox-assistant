# Demo scenario: ~20 s launch video

Storyboard for a short promo video recorded from the real web UI against the
synthetic demo mailbox. Everything shown is invented (`backend/scripts/demo_corpus.py`);
no model runs: chat answers are scripted (`backend/scripts/demo_chat.py`).
Reference frames for every beat are in [`demo-screens/`](demo-screens/).

## Story

Back from a week off: 27 emails waiting, English and French, work and
personal. The assistant brings that down to the 7 that matter, the tasks and
the week's events, and answers questions about it, all locally.

## Setup

Run from the repo root. Seed **on the day you record**: dates are relative to
the seeding day and email times to today 08:45 local time.

```bash
cd backend
uv run python -m scripts.seed_demo --reset --skip-embed --dir /tmp/inbox-demo
uv run python -m scripts.demo_server --dir /tmp/inbox-demo --port 8010 &
cd ..
BACKEND_PORT=8010 FRONTEND_PORT=5180 npx vite --strictPort &
# open http://localhost:5180/
```

No Ollama, no API key, no network calls to a model. `demo_server` swaps in the
scripted chat, skips the startup index run, and reports Ollama as up with the
default models (green "ollama · local" dot) so the header looks like a normal
install.

Recording settings (match the reference frames):

- Viewport **1920×1080**, dark UI (there is no light theme).
- Browser clock set to **08:50 today**, same timezone as the seeding machine
  (Playwright: `page.clock.install(time=…)`); otherwise chat timestamps show
  the real time.
- Locale **en-GB** (24 h clock, `07/11/2026` dates). With en-US the UI shows
  `11/7/2026` and `1:20 PM`.
- Do not open the ⚙ settings drawer: its MCP section prints the absolute
  path of the backend directory (it contains the local user name).

`backend/scripts/capture_demo_screens.py` replays every beat below and
saves the frames (see its docstring).

## Beats

| # | Time | Action | What the viewer sees | Frame |
|---|---|---|---|---|
| 1 | 0–3 s | Page loads on the **priority** tab (default). | 4 counters: 16 unread · 14 open tasks · 7 upcoming events · **7 high priority**. Tab bar `priority (7) / all mail (27)`. | `01_priority.png` |
| 2 | 3–6 s | Click the row **Opsbell · [SEV-1] checkout-api: 5xx rate at 18%**. | Email expands inline: incident details, a yellow task chip "Join the INC-3107 incident bridge · today". | `02_incident_open.png` |
| 3 ★ | 6–11 s | Type **What needs my attention today?** in the chat box, Enter. | **Hero moment.** The answer streams (~2.5 s): five bolded items (incident summary before noon, Sarah's numbers by 16:00, leaked key, MSA expiring 23:59, taxe foncière due on the 5th). | `03_attention_today.png` |
| 4 | 11–14 s | Type **Qu'est-ce que je dois faire pour l'AG de copropriété ?**, Enter. | Answer in French: AG date, signed proxy due the day before, neighbour asks for a second quote, €186,000 façade work. Shows bilingual mail. | `04_ag_french.png` |
| 5 | 14–16 s | Click the **tasks (14)** tab. | Checklist extracted from mail, each with sender and due date (`today 16:00`, `noon`, `05/11`…). | `05_tasks.png` |
| 6 | 16–19 s | Click the **events (7)** tab. | Week grouped by day: TOMORROW sprint review 10:00 → INC postmortem → dentist → meetup → dinner → AG 18:30 → crèche closed. | `06_events.png` |
| 7 | 19–20 s | End card / logo over the events view. | | |

Extra frames, not in the 20 s cut:

- `07_events_chat.png`: **Any events this week?** answered as a 7-line list.
- `08_all_mail.png`: the **all mail (27)** tab, i.e. the noise that triage
  leaves out (newsletters, receipts, notifications; one muted sender).
- `09_summarize_fr.png`: in **all mail**, expand **Syndic Duval ·
  Convocation à l'assemblée générale du …** and click **≡ summarize**
  (that button exists only in the all mail tab): 4-bullet French summary
  and an "in context" chip above the input.

## Scripted chat

Exact questions (case, accents and punctuation are ignored; a few aliases
are listed in `demo_chat.py`). Any other question gets a short "demo mode"
answer listing these.

1. `What needs my attention today?`
2. `Qu'est-ce que je dois faire pour l'AG de copropriété ?`
3. `Summarize the INC-3107 thread`
4. `Any events this week?`

**≡ summarize** has scripted answers for the incident thread (3 emails),
the syndic thread (2), the tax notice and Sarah's board-deck email.
Answers stream in 2-word chunks every 35 ms (`CHUNK_DELAY_S`). A typed
question gets its scripted answer even while an email is pinned.

## Theme

From `src/App.jsx`, `src/index.css`, `src/utils.js`, `index.html`.

Fonts (Google Fonts): **IBM Plex Mono** 400/500/600/700 for the logo, labels,
tabs, chips and timestamps; **IBM Plex Sans** 400/500/600 for email text and
chat bubbles.

| Role | Color |
|---|---|
| Page background | `#0b0d10` |
| Panels / cards | `#0e1116`, `#12151a`, `#161a20` |
| Borders | `#232830`, `#262b33` |
| Primary text | `#e8eaed`, `#e2e5ea` |
| Secondary text | `#9aa1ac`, `#6b7280` |
| Accent (logo bar, links) | `#38BDF8` |
| Primary button (send) | `#1f6feb` |
| High priority / error | `#F87171` |
| Medium priority / tasks | `#FBBF24` |
| Low priority / events / online | `#4ADE80` |
| Avatar palette | `#F87171 #FBBF24 #38BDF8 #4ADE80 #A78BFA #F472B6 #2DD4BF` |

Logo: `▍local-inbox-assistant` in Plex Mono 700, 15 px, `#e8eaed`, followed
by the "AI-assisted inbox" tagline in `#6b7280`. Favicon: dark rounded square
with a `#38BDF8` bar.
