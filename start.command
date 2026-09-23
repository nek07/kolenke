#!/bin/zsh
# Double-click to start JobBot, then open http://127.0.0.1:8765
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt && .venv/bin/python -m playwright install chromium
fi
[ -z "$NO_OPEN" ] && (sleep 2 && open http://127.0.0.1:8765) &
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765 --no-access-log
