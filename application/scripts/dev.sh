#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
  echo "Loaded $ROOT/.env"
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r backend/requirements.txt
if ! pip install -q --force-reinstall -e backend; then
  echo "Repairing venv..."
  "$(dirname "$0")/fix-venv.sh"
fi
books-cli --help >/dev/null 2>&1 || {
  echo "Repairing venv..."
  "$(dirname "$0")/fix-venv.sh"
}

if lsof -ti :8765 >/dev/null 2>&1; then
  echo "Stopping previous process on port 8765..."
  lsof -ti :8765 | xargs kill -9 2>/dev/null || true
  sleep 0.5
fi
echo "Starting books-cli serve on :8765"
books-cli serve &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT

cd desktop
if [[ ! -d node_modules ]]; then
  npm install
fi
echo "Starting Vite on http://localhost:5173"
npm run dev
