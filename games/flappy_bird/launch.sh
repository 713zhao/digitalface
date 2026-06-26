#!/bin/bash
# Launch Flappy Bird game on framebuffer LCD

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
GAMES_DIR="$(dirname "$SCRIPT_DIR")"
DIGITALFACE_DIR="$(dirname "$GAMES_DIR")"
VENV_DIR="$DIGITALFACE_DIR/.venv"

# Activate virtualenv if it exists
if [[ -f "$VENV_DIR/bin/activate" ]]; then
    source "$VENV_DIR/bin/activate"
fi

# Default framebuffer device
FBDEV="/dev/fb1"

echo "=== Flappy Bird Game ==="
echo "Framebuffer: $FBDEV"
echo "Controls: TAP TO JUMP (or SPACE)"
echo "Exit: ESC"
echo ""

# Auto-pause digitalface if it's running (needs the framebuffer)
DIGITALFACE_WAS_RUNNING=false
if systemctl is-active --quiet digitalface 2>/dev/null; then
    DIGITALFACE_WAS_RUNNING=true
    echo "⏸️  Pausing digitalface..."
    sudo systemctl stop digitalface
    sleep 1
fi

# Run game
cd "$SCRIPT_DIR"
python3 main.py --fbdev "$FBDEV" --rotate-180

# Resume digitalface if we paused it
if [[ "$DIGITALFACE_WAS_RUNNING" == "true" ]]; then
    echo ""
    echo "▶️  Resuming digitalface..."
    sudo systemctl start digitalface
fi
