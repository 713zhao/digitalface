#!/usr/bin/env bash
# Request digitalface to display a text message on the HMI screen.
#
# Usage:
#   hmi_display.sh "Your message"
#   hmi_display.sh "Your message" 10              # show for 10 seconds
#   hmi_display.sh "Your message" 10 true         # repeat every 60s until dismissed
#   hmi_display.sh "Your message" 10 90           # repeat every 90s until dismissed
#   hmi_display.sh --dismiss                       # clear active HMI overlay
#
# Repeat notifications are dismissed by touching the screen.
#
# Example (from aireminder or any other script):
#   /path/to/digitalface/hmi_display.sh "Meeting in 5 minutes!" 15 60

set -euo pipefail

RUNTIME_DIR="$(cd "$(dirname "$0")" && pwd)/.runtime"
HMI_FILE="$RUNTIME_DIR/digitalface_hmi_request"
HMI_SOCKET="$RUNTIME_DIR/digitalface_hmi.sock"

TEXT="${1:-}"
DURATION="${2:-}"
REPEAT="${3:-}"

if [[ "$TEXT" == "--dismiss" ]]; then
    HMI_TEXT="" HMI_DURATION="" HMI_REPEAT="" HMI_FILE="$HMI_FILE" HMI_SOCKET="$HMI_SOCKET" python3 -c "
import json, os, socket

payload = json.dumps({'dismiss': True}).encode('utf-8')
hmi_file = os.environ['HMI_FILE']
hmi_socket = os.environ['HMI_SOCKET']
sent = False

if os.path.exists(hmi_socket):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.sendto(payload, hmi_socket)
        s.close()
        sent = True
    except OSError:
        sent = False

if not sent:
    with open(hmi_file, 'w', encoding='utf-8') as f:
        f.write(payload.decode('utf-8'))
"
    echo "HMI dismiss request sent"
    exit 0
fi

if [[ -z "$TEXT" ]]; then
    echo "Usage: $(basename "$0") \"message\" [duration_seconds]" >&2
    exit 1
fi

mkdir -p "$RUNTIME_DIR"

HMI_TEXT="$TEXT" HMI_DURATION="$DURATION" HMI_REPEAT="$REPEAT" HMI_FILE="$HMI_FILE" HMI_SOCKET="$HMI_SOCKET" python3 -c "
import json, os, socket

text = os.environ['HMI_TEXT']
dur  = os.environ.get('HMI_DURATION', '')
rep  = os.environ.get('HMI_REPEAT', '')
hmi_file = os.environ['HMI_FILE']
hmi_socket = os.environ['HMI_SOCKET']

data = {'text': text}
if dur:
    try:
        data['duration'] = float(dur)
    except ValueError:
        pass
if rep:
    if rep.lower() == 'true':
        data['repeat'] = True
    else:
        try:
            data['repeat'] = float(rep)
        except ValueError:
            data['repeat'] = True

payload = json.dumps(data).encode('utf-8')
sent = False

if os.path.exists(hmi_socket):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.sendto(payload, hmi_socket)
        s.close()
        sent = True
    except OSError:
        sent = False

if not sent:
    with open(hmi_file, 'w', encoding='utf-8') as f:
        f.write(payload.decode('utf-8'))
"

echo "HMI request sent: \"$TEXT\"${DURATION:+ (${DURATION}s)}${REPEAT:+ repeat=${REPEAT}}"
