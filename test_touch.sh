#!/usr/bin/env bash
set -euo pipefail

# One-command touch diagnostic for DigitalFace devices.
# Usage:
#   ./test_touch.sh
#   ./test_touch.sh /dev/input/event1
#   TOUCHDEV=/dev/input/event1 ./test_touch.sh

resolve_touchdev() {
  if [[ "${1:-}" != "" ]]; then
    echo "$1"
    return 0
  fi

  if [[ "${TOUCHDEV:-}" != "" ]]; then
    echo "$TOUCHDEV"
    return 0
  fi

  local e n name
  for e in /dev/input/event*; do
    [[ -e "$e" ]] || continue
    n="$(basename "$e")"
    name="$(cat "/sys/class/input/$n/device/name" 2>/dev/null || true)"
    case "${name,,}" in
      *touch*|*ads7846*|*xpt2046*|*goodix*|*ft5*)
        echo "$e"
        return 0
        ;;
    esac
  done

  return 1
}

show_input_devices() {
  echo "Available input devices:"
  local e n name
  for e in /dev/input/event*; do
    [[ -e "$e" ]] || continue
    n="$(basename "$e")"
    name="$(cat "/sys/class/input/$n/device/name" 2>/dev/null || true)"
    printf "  %s: %s\n" "$e" "$name"
  done
}

if ! command -v evtest >/dev/null 2>&1; then
  echo "Error: evtest is not installed."
  echo "Install with: sudo apt update && sudo apt install -y evtest"
  exit 1
fi

touchdev="$(resolve_touchdev "${1:-}")" || {
  echo "Could not auto-detect touch input device."
  show_input_devices
  echo
  echo "Run again with explicit device, e.g.:"
  echo "  ./test_touch.sh /dev/input/event1"
  exit 1
}

if [[ ! -e "$touchdev" ]]; then
  echo "Error: device not found: $touchdev"
  show_input_devices
  exit 1
fi

echo "Using touch device: $touchdev"
name_file="/sys/class/input/$(basename "$touchdev")/device/name"
if [[ -f "$name_file" ]]; then
  echo "Device name: $(cat "$name_file")"
fi

echo
cat <<'MSG'
Touch test started.
Now touch the panel and watch for these events:
  - EV_ABS (X/Y coordinate updates)
  - BTN_TOUCH (press/release)

Press Ctrl+C to stop.
MSG

echo
sudo evtest "$touchdev"
