#!/usr/bin/env bash
# Start the local-inbox-assistant: Ollama check, backend + frontend.
# Installs dependencies on first run. Ctrl-C stops everything.
#
# Ports are configurable (default backend 8000, frontend 5173), either via
# environment variables or a .env file at the repo root (env vars win):
#   BACKEND_PORT=8080 FRONTEND_PORT=3000 ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

# --- configuration ----------------------------------------------------------
# CLI/environment values take precedence over .env, which beats the defaults.
_backend_port_env="${BACKEND_PORT:-}"
_frontend_port_env="${FRONTEND_PORT:-}"
[ -f .env ] && . ./.env
export BACKEND_PORT="${_backend_port_env:-${BACKEND_PORT:-8000}}"
export FRONTEND_PORT="${_frontend_port_env:-${FRONTEND_PORT:-5173}}"

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
# Each server runs in its own process group (setsid) so cleanup can kill the
# whole tree — npm/uv wrap the real vite/uvicorn processes, which would
# otherwise survive a plain kill of their parent.
echo "» starting backend on http://localhost:${BACKEND_PORT}"
setsid bash -c "cd backend && exec uv run uvicorn app.main:app --port ${BACKEND_PORT}" &
BACKEND_PID=$!

echo "» starting frontend on http://localhost:${FRONTEND_PORT}"
setsid bash -c "exec npm run dev -- --port ${FRONTEND_PORT} --strictPort" &
FRONTEND_PID=$!

cleanup() {
    trap - INT TERM EXIT
    echo
    echo "» stopping…"
    kill -TERM -"$BACKEND_PID" -"$FRONTEND_PID" 2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# If either server dies, shut the other down too.
wait -n "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
cleanup
