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

If Ollama is not running, the script tells you how to start it
(`sudo systemctl start ollama` or `ollama serve`) but leaves that to you;
pass `--start-ollama` to let the script launch `ollama serve` itself.

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

## Testing

Backend — **pytest** (99 tests, ~1 s). Everything runs against temporary
maildirs/DBs with all Ollama traffic faked (`respx` / monkeypatching) — the
real mailbox, index, and network are never touched:

```bash
cd backend
uv run pytest            # uv sync installs the dev group on first run
uv run pytest -v tests/test_parser.py   # a single file, verbose
```

| File | Covers |
|------|--------|
| `tests/test_parser.py` | `.eml` parsing: plain/HTML/multipart bodies, UTF-8 / quoted-printable / ISO-8859-1 (French), missing date/subject/sender, snippet+body truncation, unread detection (X-Mozilla-Status, maildir flags), thread headers, cheap date-only probe |
| `tests/test_maildir.py` | 90-day window scan: date filtering, mtime pre-filter vs old resynced mail, already-indexed skip, oldest-first sort, undated files, subdirectories |
| `tests/test_chunking.py` | chunking: sizes, overlap, paragraph-boundary preference, full-text coverage, micro-chunk tail regression, per-email chunk docs (header prefix, ids, metadata) |
| `tests/test_rag_store.py` | Chroma store: index/search roundtrip, idempotent upsert, deletes, empty index, and `search_emails` per-email dedup/caps |
| `tests/test_db.py` | schema idempotence, meta upsert, maildir-file uniqueness, task/event cascade delete |
| `tests/test_extract.py` | extraction window/limit selection, storing priority/tasks/events, invalid-priority coercion, blank-item skipping, 5-item caps + truncation, re-run replacement, failure marking |
| `tests/test_chat.py` | RAG prompt building: context vs no-context system prompts, excerpt/task/event injection, done-task exclusion, 12-message history cap, stream orchestration |
| `tests/test_ollama_client.py` | Ollama HTTP client (mocked with respx): availability, model list, token streaming, `think:false` only for thinking-capable models (cached probe), JSON mode with schema, embeddings, error surfacing |
| `tests/test_claude_placeholder.py` | the step-2 Claude stub: unavailable, key detection, explicit NotImplementedError |
| `tests/test_indexer.py` | full pipeline on synthetic maildirs: parse→embed→extract, incremental re-runs (one extraction per email ever), duplicate insert skip, per-email parse/extract failure tolerance, error phase reporting, `do_extract=False` |
| `tests/test_api.py` | FastAPI routes via TestClient: `/status` (ollama up/down), `/stats`, email list/filter/detail/404, tasks with toggle roundtrip + 404, events, reindex start/refusal-while-running, chat validation (400), Claude SSE error event, SSE token stream + done, mid-stream failure error event |

Frontend — **Vitest + React Testing Library** (35 tests, jsdom). Vitest is the
Vite-native unit-test runner; Playwright would be the tool for full-browser
end-to-end tests and could be added later on top of these:

```bash
npm test                 # single run
npm run test:watch       # watch mode
```

| File | Covers |
|------|--------|
| `src/test/utils.test.js` | pure helpers: priority dot colors (incl. not-yet-extracted), deterministic avatar palette, today/yesterday/older email times, relative "last indexed" times, event date chips incl. the French `dd/mm/yyyy` regression and unparseable fallback |
| `src/test/api.test.js` | API client: endpoint paths/methods, HTTP error propagation, SSE streaming (token order, frames split across network chunks, `done` termination, `error` events thrown, no tokens after error, exact request payload) |
| `src/test/App.test.jsx` | dashboard behavior with a mocked API: live header status (ollama up/down, claude "soon"), stat tiles, filter switching + correct queries, email expansion with task/event chips, task toggle calling the API, event date chips, settings drawer (real index numbers, MCP register command, Claude placeholder), disabled Claude model option, chat send → streamed answer rendering, chat error bubbles, backend-unreachable banner, indexing progress display |

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

## License

[MIT](LICENSE). All dependencies are under MIT-compatible permissive licenses
(MIT, BSD-3-Clause, Apache-2.0).
