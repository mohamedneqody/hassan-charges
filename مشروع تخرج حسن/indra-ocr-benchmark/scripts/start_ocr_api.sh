#!/usr/bin/env bash
# Start the Indra OCR local API detached inside WSL (survives the terminal).
# Usage:  bash scripts/start_ocr_api.sh [port]     (default 8000)
set -u
PY="$HOME/indra-ocr-bench/.venv/bin/python"
PROJ="/mnt/d/hassan_charges/مشروع تخرج حسن/indra-ocr-benchmark"
PORT="${1:-8900}"
PIDFILE="$PROJ/logs/ocr_api.pid"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "already running (pid $(cat "$PIDFILE"))"
  exit 0
fi
mkdir -p "$PROJ/logs"
nohup "$PY" "$PROJ/scripts/ocr_api.py" --port "$PORT" --threads 4 \
  > "$PROJ/logs/ocr_api.log" 2>&1 &
echo $! > "$PIDFILE"
sleep 2
if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "started pid $(cat "$PIDFILE") on port $PORT | log: logs/ocr_api.log"
  curl -s "http://localhost:$PORT/health" || true
else
  echo "FAILED to start - see logs/ocr_api.log"
  tail -5 "$PROJ/logs/ocr_api.log"
fi
