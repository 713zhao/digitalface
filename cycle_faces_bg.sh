#!/usr/bin/env bash
set -euo pipefail

INTERVAL="${1:-6}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="$SCRIPT_DIR/.runtime"
PID_FILE="$RUNTIME_DIR/digitalface_cycle.pid"
CONTROL_FILE="$RUNTIME_DIR/digitalface_expression"
LOG_FILE="$RUNTIME_DIR/digitalface_cycle.log"
FACES=(happy neutral listening surprised)

mkdir -p "$RUNTIME_DIR"
touch "$CONTROL_FILE"
chmod 666 "$CONTROL_FILE" || true

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
) >"$LOG_FILE" 2>&1 &

echo "cycle started"
