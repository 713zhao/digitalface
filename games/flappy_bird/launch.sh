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

# Check if --sdl flag is passed
SDL_MODE=false
if [[ "$1" == "--sdl" ]]; then
    SDL_MODE=true
    FBDEV="/dev/fb1"
fi

echo "=== Flappy Bird Game ==="
if [[ "$SDL_MODE" == "true" ]]; then
    echo "Mode: SDL Window (for testing)"
    echo "Controls: SPACE TO JUMP"
else
    echo "Framebuffer: $FBDEV"
    echo "Controls: TAP TO JUMP (or SPACE)"
    echo ""
    echo "⚠️  IMPORTANT: If you see 'fbcon not available' error:"
    echo "   Stop digitalface first: sudo systemctl stop digitalface"
    echo "   Then run this script again"
fi
echo "Exit: ESC or close window"
echo ""

# Run game
cd "$SCRIPT_DIR"
if [[ "$SDL_MODE" == "true" ]]; then
    python3 main.py --sdl
else
    python3 main.py --fbdev "$FBDEV"
fi
