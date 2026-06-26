#!/bin/bash
# Launch Flappy Bird game on framebuffer LCD

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
GAMES_DIR="$(dirname "$SCRIPT_DIR")"
DIGITALFACE_DIR="$(dirname "$GAMES_DIR")"
VENV_DIR="$DIGITALFACE_DIR/.venv"

# Activate virtualenv if it exists
if [[ -f "$VENV_DIR/bin/activate" ]]; then
    source "$VENV_DIR/bin/activate"
fi

# Default framebuffer device
FBDEV="${1:-/dev/fb1}"

echo "=== Flappy Bird Game ==="
echo "Framebuffer: $FBDEV"
echo "Controls: TAP TO JUMP (or SPACE)"
echo "Exit: ESC or close window"
echo ""

# Run game
cd "$SCRIPT_DIR"
python3 main.py --fbdev "$FBDEV"
