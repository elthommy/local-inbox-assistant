#!/usr/bin/env bash
# Start the local-inbox-assistant: Ollama check, backend (:8000) + frontend (:5173).
# Installs dependencies on first run. Ctrl-C stops everything.
set -euo pipefail
cd "$(dirname "$0")"

# --- dependencies -----------------------------------------------------------
command -v uv >/dev/null || { echo "error: uv is required (https://docs.astral.sh/uv/)"; exit 1; }
command -v npm >/dev/null || { echo "error: npm is required"; exit 1; }

[ -d backend/.venv ] || { echo "» installing backend dependencies (uv sync)…"; (cd backend && uv sync); }
[ -d node_modules ] || { echo "» installing frontend dependencies (npm install)…"; npm install; }

# --- ollama -----------------------------------------------------------------
if ! curl -sf --max-time 2 http://localhost:11434/api/tags >/dev/null; then
    if command -v ollama >/dev/null; then
        echo "» starting ollama serve…"
        nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
        for _ in $(seq 1 20); do
            curl -sf --max-time 2 http://localhost:11434/api/tags >/dev/null && break
            sleep 0.5
        done
    else
        echo "warning: ollama not found — chat and indexing will fail until it runs"
    fi
fi

# --- servers ----------------------------------------------------------------
cleanup() { echo; echo "» stopping…"; kill 0; }
trap cleanup INT TERM

echo "» starting backend on http://localhost:8000"
(cd backend && exec uv run uvicorn app.main:app --port 8000) &

echo "» starting frontend on http://localhost:5173"
npm run dev &

wait
