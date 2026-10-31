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
