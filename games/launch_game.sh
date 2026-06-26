#!/bin/bash
# Games Launcher - Choose and run a game

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo ""
echo "╔════════════════════════════════════════╗"
echo "║          DIGITALFACE GAMES             ║"
echo "╚════════════════════════════════════════╝"
echo ""

# List available games
games=()
for dir in "$SCRIPT_DIR"/*/; do
    if [[ -f "$dir/launch.sh" ]]; then
        game_name=$(basename "$dir")
        games+=("$game_name")
    fi
done

if [[ ${#games[@]} -eq 0 ]]; then
    echo "❌ No games found!"
    exit 1
fi

echo "Available games:"
for i in "${!games[@]}"; do
    echo "  $((i+1)). ${games[$i]}"
done
echo ""

# If argument provided, use it; otherwise ask user
if [[ -n "$1" ]]; then
    choice=$1
else
    read -p "Select game (1-${#games[@]}): " choice
fi

# Validate choice
if ! [[ "$choice" =~ ^[0-9]+$ ]] || [[ $choice -lt 1 ]] || [[ $choice -gt ${#games[@]} ]]; then
    echo "❌ Invalid choice!"
    exit 1
fi

selected_game="${games[$((choice-1))]}"
echo ""
echo "🎮 Launching $selected_game..."
echo ""

# Run the game
"$SCRIPT_DIR/$selected_game/launch.sh" "$2"
