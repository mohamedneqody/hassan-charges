#!/usr/bin/env bash
# Stop the Indra OCR local API started by start_ocr_api.sh
set -u
PROJ="/mnt/d/hassan_charges/مشروع تخرج حسن/indra-ocr-benchmark"
PIDFILE="$PROJ/logs/ocr_api.pid"
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  kill "$(cat "$PIDFILE")"
  rm -f "$PIDFILE"
  echo "stopped"
else
  echo "not running"
fi
