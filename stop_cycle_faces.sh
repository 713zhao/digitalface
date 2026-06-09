#!/usr/bin/env bash
set -euo pipefail

PID_FILE="/tmp/digitalface_cycle.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "cycle not running"
  exit 0
fi

pid="$(cat "$PID_FILE" || true)"
if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
  kill "$pid" || true
fi
rm -f "$PID_FILE"
echo "cycle stopped"
