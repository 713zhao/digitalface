#!/usr/bin/env bash
set -euo pipefail

INTERVAL="${1:-6}"
PID_FILE="/tmp/digitalface_cycle.pid"
CONTROL_FILE="/tmp/digitalface_expression"
FACES=(happy neutral listening surprised)

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" || true)"
  if [[ -n "${old_pid:-}" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "cycle already running with PID $old_pid"
    exit 0
  fi
fi

(
  echo $$ > "$PID_FILE"
  idx=0
  while true; do
    echo "${FACES[$idx]}" > "$CONTROL_FILE"
    idx=$(( (idx + 1) % ${#FACES[@]} ))
    sleep "$INTERVAL"
  done
) >/tmp/digitalface_cycle.log 2>&1 &

echo "cycle started"
