# local-inbox-assistant

A fully local, AI-assisted inbox dashboard. It indexes your Thunderbird Gmail
maildir (`.eml` files), answers questions about your mail with a local Ollama
model over a RAG index, extracts tasks / events / priority from recent emails,
and exposes the same data to other AI tools through an MCP server.

Nothing leaves your machine: parsing, embeddings (ChromaDB + `nomic-embed-text`),
and chat all run locally. Claude cloud support is planned as a second step —
the UI shows it as "coming soon".

## Architecture

- **`backend/`** — Python (FastAPI, uv-managed, Python 3.12)
  - Maildir scanner + `.eml` parser (stdlib `email`, HTML→text fallback)
  - Incremental indexer: parse → embed (Ollama `nomic-embed-text` → ChromaDB)
    → LLM extraction of priority/tasks/events on recent mail
  - REST API + SSE streaming chat with RAG context
  - `mcp_server.py` — stdio MCP server (`search_mail`, `get_thread`,
    `list_tasks`, `list_events`)
- **`src/`** — React + Vite frontend (two-pane dashboard: chat + inbox)

## Requirements

- [Ollama](https://ollama.com) running locally with:
  - an instruct model for chat/extraction (default: `qwen3.6`)
  - `nomic-embed-text` for embeddings (`ollama pull nomic-embed-text`)
- [uv](https://docs.astral.sh/uv/) (manages Python 3.12 + deps)
- Node.js for the frontend
- A Thunderbird profile storing mail in maildir format

## Run

```bash
./start.sh             # installs deps on first run, starts everything; Ctrl-C stops it
```

By default the frontend is at http://localhost:5173 and the backend at :8000.
Ports are configurable via env vars or a `.env` file at the repo root (see
`.env.example`; env vars take precedence):

```bash
BACKEND_PORT=8080 FRONTEND_PORT=3000 ./start.sh
```

Or start the pieces manually:

```bash
# 1. backend (first start indexes the last 90 days of mail; watch progress in the UI)
cd backend
uv sync
uv run uvicorn app.main:app --port 8000

# 2. frontend
npm install
npm run dev            # http://localhost:5173 (proxies /api to :8000)
```

Backend configuration lives in `backend/.env` (see `backend/.env.example`):
maildir path, indexing window, model names, Ollama URL.

## MCP server

Expose the indexed inbox to Claude Code / Claude Desktop:

```bash
claude mcp add localmail -- uv --directory /absolute/path/to/backend run python mcp_server.py
```

Tools: `search_mail(query, top_k)`, `get_thread(message_id)`,
`list_tasks(include_done)`, `list_events(limit)`. The exact register command
(with the right absolute path) is shown in the app under **⚙ MCP / RAG →
MCP server**.

## Notes

- **Indexing** is incremental: already-seen maildir files are skipped, and the
  LLM extraction pass runs once per email (last 14 days by default — one local
  LLM call per email).
- **Unread status** is best-effort: Thunderbird keeps live read-state in its
  `.msf` index, which is not parsed; the `X-Mozilla-Status` header snapshot is
  used instead.
- **Data** lives in `backend/data/` (SQLite + ChromaDB); delete the folder to
  rebuild from scratch.
- **Claude (step 2)**: `backend/app/llm/claude.py` is the placeholder provider;
  the settings drawer and model dropdown already reserve the UI slots.
