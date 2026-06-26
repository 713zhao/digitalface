# Protocol v2: HMI Overlay Message Format

Communication protocol for sending messages to the digitalface LCD display via Unix datagram sockets.

## Socket Configuration

- **Location**: `/home/eric/projects/digitalface/.runtime/digitalface_hmi.sock`
- **Type**: AF_UNIX (Unix domain socket)
- **Socket Style**: SOCK_DGRAM (datagram)
- **Permissions**: 0o666 (world-writable for multi-user access)
- **Fallback**: `/home/eric/projects/digitalface/.runtime/digitalface_hmi_request` (file-based IPC)

## Message Format

### Display Messages (text, pic, alert)

Send a JSON payload to the socket:

```json
{
  "id": "unique-message-id",
  "type": "text",
  "text": "Your message here",
  "duration": 10,
  "priority": "normal",
  "font_size": 80,
  "animation": "none",
  "animation_duration": 0.5,
  "sound": false,
  "persistent": false,
  "tags": ["reminder", "urgent"]
}
```

### Dismiss Messages

Dismiss a specific message by ID:

```json
{
  "dismiss": "unique-message-id"
}
```

Dismiss all messages:

```json
{
  "dismiss": true
}
```

## Field Specifications

### Required Fields

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `type` | string | Message type | `"text"`, `"pic"`, or `"alert"` |
| `duration` | number | Display duration in seconds | ≥ 1.0 seconds |

### Required for Specific Types

- **`type: "text"`**: `text` field must be non-empty string
- **`type: "pic"`**: `image_path` field must point to valid image file
- **`type: "alert"`**: `text` field must be non-empty string

### Optional Fields

| Field | Type | Default | Description | Constraints |
|-------|------|---------|-------------|-------------|
| `id` | string | UUID v4 | Unique message identifier (generated if omitted) | max 256 chars |
| `text` | string | `""` | Message content (required for text/alert) | auto-wrapped at screen width |
| `image_path` | string | null | Path to image file (required for pic) | absolute or relative path |
| `priority` | string | `"normal"` | Queue priority | `"low"`, `"normal"`, `"high"` |
| `font_size` | number | `80` | Text font size in pixels | 8–128, clamped on sender and receiver |
| `animation` | string | `"none"` | Animation effect | See Animation Types section |
| `animation_duration` | number | `0.5` | Animation duration in seconds | 0.1–5.0 seconds, clamped |
| `sound` | boolean | `false` | Play sound on display (future feature) | Currently ignored |
| `persistent` | boolean | `false` | Display indefinitely (ignore duration) | Duration still sent for reference |
| `tags` | array | `[]` | Metadata tags for filtering | array of strings |

## Animation Types

| Type | Description | Duration | Visual Effect |
|------|-------------|----------|----------------|
| `"none"` | No animation | N/A | Static display |
| `"fade_in"` | Fade from transparent to opaque | user-defined | Alpha: 0 → 1 |
| `"fade_out"` | Fade from opaque to transparent | user-defined | Alpha: 1 → 0 |
| `"pulse"` | Pulsing brightness effect | user-defined | Alpha: 0.5 → 1.0 → 0.5 (continuous) |
| `"blink"` | Blinking on/off | user-defined | Alpha: 1.0 ↔ 0.3 (every 0.2s) |
| `"typewriter"` | Type text character by character | user-defined | Char count: 0 → text length |
| `"zoom_in"` | Scale up from 50% to 100% | user-defined | Scale: 0.5 → 1.0 |
| `"zoom_out"` | Scale down from 100% to 70% | user-defined | Scale: 1.0 → 0.7 |

## Display Features

### Text Wrapping & Scrolling

- Text automatically wraps to fit screen width based on font size
- If wrapped text height exceeds available space:
  - Text scrolls vertically from **bottom to top**
  - Scroll speed: **30 pixels/second**
  - Continuous seamless loop with 50px gap between repeats
- Available space reserves 60 pixels for progress bar at bottom

### Progress Bar

- Displays at bottom of screen
- Shows remaining time as colored bar
- Full width bar = full duration remaining
- Empty bar = message about to expire
- Disabled for `persistent: true` messages

### Priority Queuing

Messages are queued and displayed in order:

1. **High priority** messages first (earliest arrival time as tiebreaker)
2. **Normal priority** messages second
3. **Low priority** messages last

When a message expires or is dismissed, the next queued message displays automatically.

### Message Types

#### Type: "text"

Displays text message with optional animation.

```json
{
  "id": "msg-text-001",
  "type": "text",
  "text": "This is a text message that will wrap and scroll if too long",
  "duration": 15,
  "font_size": 80,
  "animation": "fade_in",
  "animation_duration": 1.0,
  "priority": "normal"
}
```

#### Type: "pic"

Displays image with optional text overlay (future: text overlay).

```json
{
  "id": "msg-pic-001",
  "type": "pic",
  "image_path": "/path/to/image.png",
  "duration": 10,
  "animation": "zoom_in",
  "animation_duration": 0.5,
  "priority": "high"
}
```

#### Type: "alert"

Displays alert message (typically with high priority and sound).

```json
{
  "id": "msg-alert-001",
  "type": "alert",
  "text": "ALERT: System notification",
  "duration": 8,
  "priority": "high",
  "sound": true,
  "font_size": 80
}
```

## Python Examples

### Basic Text Message

```python
import socket
import json
import uuid

def send_hmi_message(text, duration=10, font_size=80):
    payload = {
        "id": str(uuid.uuid4()),
        "type": "text",
        "text": text,
        "duration": duration,
        "font_size": font_size,
        "priority": "normal"
    }
    
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.sendto(
            json.dumps(payload).encode(),
            "/home/eric/projects/digitalface/.runtime/digitalface_hmi.sock"
        )
        print(f"Message sent: {payload['id']}")
        return payload['id']
    except Exception as e:
        print(f"Failed to send: {e}")
        return None
    finally:
        sock.close()

# Usage
msg_id = send_hmi_message("Hello World!", duration=5, font_size=80)
```

### With Animation

```python
import socket
import json
import uuid

payload = {
    "id": str(uuid.uuid4()),
    "type": "text",
    "text": "Animated message with fade effect",
    "duration": 8,
    "font_size": 50,
    "animation": "fade_in",
    "animation_duration": 2.0,
    "priority": "normal"
}

sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
sock.sendto(json.dumps(payload).encode(), "/home/eric/projects/digitalface/.runtime/digitalface_hmi.sock")
sock.close()
```

### Dismiss Message

```python
import socket
import json

# Dismiss specific message
dismiss_payload = {
    "dismiss": "message-id-to-dismiss"
}

sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
sock.sendto(json.dumps(dismiss_payload).encode(), "/home/eric/projects/digitalface/.runtime/digitalface_hmi.sock")
sock.close()

# Dismiss all
dismiss_all = {"dismiss": True}
sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
sock.sendto(json.dumps(dismiss_all).encode(), "/home/eric/projects/digitalface/.runtime/digitalface_hmi.sock")
sock.close()
```

### Display Image

```python
import socket
import json
import uuid

payload = {
    "id": str(uuid.uuid4()),
    "type": "pic",
    "image_path": "/home/eric/images/icon.png",
    "duration": 10,
    "animation": "zoom_in",
    "animation_duration": 1.0,
    "priority": "normal"
}

sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
sock.sendto(json.dumps(payload).encode(), "/home/eric/projects/digitalface/.runtime/digitalface_hmi.sock")
sock.close()
```

### High Priority Alert

```python
import socket
import json
import uuid

payload = {
    "id": str(uuid.uuid4()),
    "type": "alert",
    "text": "URGENT: System maintenance scheduled",
    "duration": 15,
    "priority": "high",
    "sound": True,
    "font_size": 80,
    "animation": "blink",
    "animation_duration": 2.0
}

sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
sock.sendto(json.dumps(payload).encode(), "/home/eric/projects/digitalface/.runtime/digitalface_hmi.sock")
sock.close()
```

## Command-Line Tool (trigger-lcd)

Located in `/home/eric/projects/aireminder/mcp/python/trigger-lcd`

### Show Message

```bash
./trigger-lcd show "Your message text"
./trigger-lcd show "Text" -d 5                          # 5 seconds
./trigger-lcd show "Text" --font-size 50                # 50px font
./trigger-lcd show "Text" --animation fade_in           # With fade-in
./trigger-lcd show "Text" --animation typewriter --animation-duration 2.0
./trigger-lcd show "Image text" --type pic --image-path /path/to/img.png
```

### Dismiss Messages

```bash
./trigger-lcd dismiss <message-id>                      # Dismiss by ID
./trigger-lcd dismiss-all                               # Dismiss all
```

### Test Suite

```bash
./trigger-lcd test                                      # Run animation tests
```

## Error Handling

- **Invalid JSON**: Message ignored, logged in systemd journal
- **Missing required fields**: Message rejected with validation error
- **Invalid type**: Message rejected
- **Image load failure (pic type)**: Message discarded, fallback to next queue
- **Socket send failure**: Automatic fallback to file-based IPC
- **Oversized message**: Truncated to reasonable limits or split

## Performance Notes

- Messages are non-blocking (async send)
- Socket polling interval: 100ms
- Text wrapping calculated once per message (cached)
- Image scaling and caching for performance
- Animation frame rate: 30 FPS (tied to display refresh)

## Backward Compatibility

Protocol v2 is backward-compatible with v1:
- All new fields are optional with sensible defaults
- Existing systems sending minimal payloads continue to work
- Animation, priorities, and custom fonts are additive features

## Troubleshooting

### Message not displaying

1. Check socket exists: `ls -la /home/eric/projects/digitalface/.runtime/digitalface_hmi.sock`
2. Check permissions: `stat .runtime/digitalface_hmi.sock` (should be 0o666)
3. Verify digitalface is running: `systemctl status digitalface`
4. Check logs: `journalctl -u digitalface -n 50 --no-pager`
5. Ensure JSON is valid: Use `python3 -m json.tool` to validate

### Text not wrapping correctly

- Font size affects wrap point (larger font = fewer chars per line)
- Screen width is 480 pixels with 36px padding (available: 408px)
- Test with `--font-size 80` which should wrap most text

### Animation not smooth

- Check display refresh rate (should be 30 FPS)
- Verify message `duration` is long enough for animation + display time
- Animation duration shouldn't exceed display duration

### Image not displaying

- Verify image file exists and is readable
- Supported formats: PNG, JPG, BMP (via Pygame)
- Try absolute path instead of relative
- Check file permissions: `ls -la /path/to/image.png`
