#!/usr/bin/env bash
set -euo pipefail

FACE="${1:-happy}"
CONTROL_FILE="/tmp/digitalface_expression"

case "$FACE" in
  neutral|happy|listening|surprised)
    ;;
  *)
    echo "Usage: $0 {neutral|happy|listening|surprised}"
    exit 1
    ;;
esac

echo "$FACE" > "$CONTROL_FILE"
echo "Face set to: $FACE"
