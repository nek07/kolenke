#!/bin/zsh
# Double-click to start kolenke: the API (FastAPI, 127.0.0.1:8765) and the page (Next.js, 127.0.0.1:3000).
# The first start installs everything; later starts rebuild the page only when its code changed.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Первый запуск: устанавливаю kolenke…"
  python3 -m venv .venv
  .venv/bin/pip install -q -e "backend[dev]"
  .venv/bin/python -m playwright install chromium
fi

if ! command -v npm >/dev/null; then
  echo "Нужен Node.js 20.9+ для интерфейса: https://nodejs.org или brew install node"
  exit 1
fi
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm ci --no-fund --no-audit)
fi
# rebuild when any page source is newer than the last build
if [ ! -f frontend/.next/BUILD_ID ] || [ -n "$(find frontend/src frontend/next.config.ts frontend/package.json -newer frontend/.next/BUILD_ID -print -quit)" ]; then
  (cd frontend && npm run build)
fi

(cd backend && ../.venv/bin/uvicorn kolenke.main:app --host 127.0.0.1 --port 8765) &
API=$!
(cd frontend && npm run start -- --hostname 127.0.0.1) &
WEB=$!
trap 'kill $API $WEB 2>/dev/null' EXIT INT TERM

[ -z "$NO_OPEN" ] && (sleep 3 && open http://127.0.0.1:3000) &
wait
