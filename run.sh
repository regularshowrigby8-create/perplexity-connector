#!/usr/bin/env bash
# One command. No config, no keys, no setup steps.
set -euo pipefail
cd "$(dirname "$0")"

PY_BIN="${PYTHON:-python3}"
if [ ! -x .venv/bin/python ]; then
  echo "→ creating virtualenv"
  "$PY_BIN" -m venv .venv
fi

if [ ! -f .venv/.deps-ok ]; then
  echo "→ installing engine dependencies (one time)"
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r apps/api/requirements.txt
  touch .venv/.deps-ok
fi

if [ ! -d apps/web/node_modules ]; then
  echo "→ installing interface"
  (cd apps/web && npm install --no-audit --no-fund)
fi

mkdir -p data
echo "→ api  http://0.0.0.0:8000"
(cd apps/api && ../../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level warning) &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT

for _ in $(seq 1 40); do
  if curl -sf http://127.0.0.1:8000/healthz >/dev/null 2>&1; then break; fi
  sleep 0.5
done

echo "→ web  http://0.0.0.0:3000"
cd apps/web && API_URL=http://127.0.0.1:8000 npm run dev
