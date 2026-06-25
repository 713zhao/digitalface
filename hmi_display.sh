#!/usr/bin/env bash
# Request digitalface to display a text message on the HMI screen.
#
# Usage:
#   hmi_display.sh "Your message here"
#   hmi_display.sh "Your message here" 15          # show for 15 seconds
#
# The request file is picked up by digitalface within ~0.1s.
# If no duration is given, digitalface uses its default (10 seconds).
#
# Example (from aireminder or any other script):
#   /path/to/digitalface/hmi_display.sh "Meeting in 5 minutes!" 20

set -euo pipefail

RUNTIME_DIR="$(cd "$(dirname "$0")" && pwd)/.runtime"
HMI_FILE="$RUNTIME_DIR/digitalface_hmi_request"

TEXT="${1:-}"
DURATION="${2:-}"

if [[ -z "$TEXT" ]]; then
    echo "Usage: $(basename "$0") \"message\" [duration_seconds]" >&2
    exit 1
fi

mkdir -p "$RUNTIME_DIR"

HMI_TEXT="$TEXT" HMI_DURATION="$DURATION" HMI_FILE="$HMI_FILE" python3 -c "
import json, os
text = os.environ['HMI_TEXT']
dur  = os.environ.get('HMI_DURATION', '')
data = {'text': text}
if dur:
    try:
        data['duration'] = float(dur)
    except ValueError:
        pass
with open(os.environ['HMI_FILE'], 'w', encoding='utf-8') as f:
    json.dump(data, f)
"

echo "HMI request sent: \"$TEXT\"${DURATION:+ (${DURATION}s)}"
