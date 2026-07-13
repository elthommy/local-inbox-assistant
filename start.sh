#!/usr/bin/env bash
# Start the local-inbox-assistant: Ollama check, backend + frontend.
# Installs dependencies on first run. Ctrl-C stops everything.
#
# Ports are configurable (default backend 8000, frontend 5173), either via
# environment variables or a .env file at the repo root (env vars win):
#   BACKEND_PORT=8080 FRONTEND_PORT=3000 ./start.sh
#
# If Ollama is not running, the script tells you how to start it but does not
# start it for you unless you pass --start-ollama.
set -euo pipefail
cd "$(dirname "$0")"

START_OLLAMA=0
for arg in "$@"; do
    case "$arg" in
        --start-ollama) START_OLLAMA=1 ;;
        -h|--help)
            echo "usage: $0 [--start-ollama]"
            echo "  --start-ollama   launch 'ollama serve' if Ollama is not already running"
            exit 0 ;;
        *) echo "error: unknown option '$arg' (see --help)"; exit 1 ;;
    esac
done

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
ollama_up() { curl -sf --max-time 2 http://localhost:11434/api/tags >/dev/null; }

if ! ollama_up; then
    if ! command -v ollama >/dev/null; then
        echo "warning: ollama not found — chat and indexing will fail until it runs"
        echo "         install it from https://ollama.com, then restart this script"
    elif [ "$START_OLLAMA" = 1 ]; then
        echo "» starting ollama serve…"
        nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
        for _ in $(seq 1 20); do
            ollama_up && break
            sleep 0.5
        done
        ollama_up || echo "warning: ollama did not come up (see /tmp/ollama-serve.log)"
    else
        echo "warning: ollama is not running — chat and indexing will fail until it is."
        echo "         Start it yourself with one of:"
        if command -v systemctl >/dev/null \
           && systemctl list-unit-files ollama.service >/dev/null 2>&1 \
           && [ -n "$(systemctl list-unit-files ollama.service --no-legend 2>/dev/null)" ]; then
            echo "           sudo systemctl start ollama"
        fi
        echo "           ollama serve"
        echo "         or re-run with: $0 --start-ollama"
    fi
fi

# Without Ollama the backend can only fall back to the Claude cloud provider,
# which needs INBOX_ANTHROPIC_API_KEY (environment or backend/.env). If Ollama
# is still down and no key is configured, no inference server is reachable.
if ! ollama_up; then
    # A key sourced from the root .env must be exported to reach the backend.
    [ -n "${INBOX_ANTHROPIC_API_KEY:-}" ] && export INBOX_ANTHROPIC_API_KEY
    if [ -z "${INBOX_ANTHROPIC_API_KEY:-}" ] \
       && ! grep -Eqs '^[[:space:]]*INBOX_ANTHROPIC_API_KEY[[:space:]]*=[[:space:]]*[^[:space:]]' backend/.env; then
        echo "error: ollama is not running and no Claude API key is configured —"
        echo "       the backend has no inference server to connect to."
        exit 1
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
setsid bash -c "exec npm run dev -- --port ${FRONTEND_PORT} --strictPort --clearScreen false" &
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
