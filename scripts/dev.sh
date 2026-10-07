#!/usr/bin/env bash
set -euo pipefail

DB="${EIDOS_DB:-.eidos/traces.db}"
API_PORT="${EIDOS_API_PORT:-8765}"
UI_PORT="${EIDOS_UI_PORT:-5173}"

if [[ ! -d ui/node_modules ]]; then
  (cd ui && bun install)
fi

uv run eidos serve "$DB" --host 127.0.0.1 --port "$API_PORT" &
api_pid=$!

cleanup() {
  kill "$api_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Eidos API: http://127.0.0.1:$API_PORT"
echo "Eidos UI:  http://127.0.0.1:$UI_PORT"

(cd ui && bun run dev -- --host 127.0.0.1 --port "$UI_PORT")
