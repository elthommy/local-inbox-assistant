# AGENTS.md

## Security model

- **Trust boundary:** single-user app on the user's own machine. The backend
  (uvicorn, default bind `127.0.0.1:8000`) and the Vite dev server
  (`localhost:5173`, proxies `/api`) listen on loopback only. The MCP server
  (`backend/mcp_server.py`) runs over stdio, launched by the user's MCP client.
- **Intended:** no authentication on the HTTP API. Other processes running as
  the same OS user are trusted (they can read `backend/data/` and the maildir
  directly anyway). Environment variables and `.env` files are trusted.
- **Untrusted input:** email content from the Thunderbird maildir (headers,
  HTML/text bodies, attachment names) — anyone can send the user an email —
  plus LLM output derived from it, and any web page open in the user's browser.
- **Attackers that matter:**
  1. **Remote email sender** — XSS via rendered email/markdown, injection via
     headers or filenames, prompt injection that leads to *actions* (not just
     text).
  2. **Malicious website** in the user's browser — CSRF on state-changing
     endpoints, CORS misconfiguration, DNS rebinding against `:8000` / `:5173`
     to read the mailbox.
  3. **LAN attacker** — only if something binds beyond loopback.
- **Out of scope:** local same-user attackers, physical access, and
  Anthropic/Ollama themselves. Email excerpts are sent to Claude only when the
  user picks Claude for a chat.

## Long-running GPU jobs (benchmarks, bulk re-extraction)

The GPU is shared with the user's own work: they may need it back at any
time. Any script that keeps Ollama busy for more than a few minutes —
including throwaway scripts in a scratchpad — MUST follow this contract.

**Script requirements**
1. **Checkpoint in small chunks.** Save results after each chunk of at most
   ~2 minutes of work, with an atomic write (`tmp` file + `os.replace`), so a
   hard kill loses at most one chunk.
2. **Resume by skipping done work.** On start, load the saved state and skip
   every item already in it; re-running the same command continues the job.
3. **Graceful stop via a `STOP` file** in the script's directory: check it
   after every chunk; when present, save, unload the model and exit with a
   log line containing `stopped cleanly`. Delete a leftover `STOP` on start.
4. **Always release the GPU** on exit (finish, stop or crash), in a
   `finally`: unload the model with
   `POST /api/chat {"model": "<name>", "messages": [], "keep_alive": 0}`.
5. **Bound slow candidates.** When screening models, drop one whose first few
   items are far over the speed budget instead of finishing the screen.
6. **Log progress to a file** (one line per chunk) and run the job in the
   background, so a stop/resume never depends on the launching session.

The first job built this way (2026-10-31 model benchmark) kept its state in a
single JSON file keyed by job then item id, ran chunks of 10 emails, and
dropped a model whose first 3 emails averaged over 2× the speed budget.

**When the user asks to stop / get the GPU back** — the agent does it, the
user does not create the file:
1. `touch <job dir>/STOP`
2. Wait for `stopped cleanly` in the job's log (normally ≤ 2 min, must be
   ≤ 15 min).
3. Verify the GPU is free: `curl -s localhost:11434/api/ps` lists no models.
   If one is still loaded, unload it with the `keep_alive: 0` call above.
4. Only if the job does not stop within 15 min: find it with `pgrep -af
   <script name>` and `kill <pid>`. Never `pkill -f "<pattern>"` from an
   agent shell — the pattern matches the agent's own `bash -c` wrapper and
   kills it (exit 144).
5. Tell the user what was saved (items done / total) and the resume command.

**When the user gives the GPU back:** re-run the same start command; it
resumes from the saved state. Report what is left and an ETA.
