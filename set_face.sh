#!/usr/bin/env bash
set -euo pipefail

FACE="${1:-happy}"
INTERVAL="${2:-60}"
CONTROL_FILE="/tmp/digitalface_expression"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$FACE" == "auto" ]]; then
  "$SCRIPT_DIR/cycle_faces_bg.sh" "$INTERVAL"
  echo "Auto mode enabled: switching faces every ${INTERVAL}s"
  exit 0
fi

case "$FACE" in
  neutral|happy|listening|surprised)
    ;;
  *)
    echo "Usage: $0 {neutral|happy|listening|surprised|auto} [interval_seconds]"
    exit 1
    ;;
esac

echo "$FACE" > "$CONTROL_FILE"
echo "Face set to: $FACE"
