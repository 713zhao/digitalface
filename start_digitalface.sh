#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/eric/projects/digitalface"
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
FBDEV="${1:-/dev/fb1}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: venv python not found at $PYTHON_BIN"
  exit 1
fi

# Stop managed service first so it will not auto-respawn during manual restart.
if systemctl is-active --quiet digitalface.service; then
  sudo systemctl stop digitalface.service
fi

# Kill any leftover manual instances.
pkill -f '/home/eric/projects/digitalface/main.py' || true
sleep 0.3

cd "$PROJECT_DIR"
echo "Starting digitalface on $FBDEV ..."
exec "$PYTHON_BIN" main.py --force-fb --fbdev "$FBDEV"
