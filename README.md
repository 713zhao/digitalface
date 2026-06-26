# Digital Face for Raspberry Pi 4 (3.5 inch SPI LCD)

A colorful animated digital face for Raspberry Pi OS Lite + SPI LCD.

## Project Path

- /home/eric/projects/digitalface

## Architecture Reference

- See `interfaces.md` for the driver/application layer contract and extension guidelines.

## Current Features

- Fancy animated face UI with 4 expressions:
  - happy (default)
  - neutral
  - listening
  - surprised
- Framebuffer output for SPI LCD (`/dev/fb1` by default)
- Single-instance protection (prevents duplicate GUI processes)
- Runtime face switching without app restart using helper scripts
- Optional auto-cycle mode to switch faces periodically
- Double-click or double-tap the screen to switch to the next face
- Driver-level LED backlight on/off control
- Auto LED backlight off after 10 minutes of no face change and no touch input
- Touch input support in framebuffer mode to wake display
- **HMI Overlay System**: Unix socket-based IPC for displaying messages, images, and alerts
- **Protocol v2**: JSON-based message protocol with animations, priorities, and smart text scrolling
- **Text Scrolling**: Automatic vertical scrolling (bottom to top) when text exceeds screen height
- **Animation Support**: fade_in, fade_out, pulse, blink, typewriter, zoom_in, zoom_out effects
- **Message Priority**: high/normal/low queue ordering
- **Persistent Display**: Optional unlimited display duration
- **Font Size Control**: 8-128 pixels, default 80px
- **Selective Dismiss**: Dismiss messages by ID or clear all

## Requirements

- Raspberry Pi 4
- 3.5 inch SPI LCD with framebuffer driver
- Raspberry Pi OS Lite
- Python 3.11+

## Detected Hardware On This Device

From runtime detection on this Raspberry Pi:

- LCD framebuffer driver (`/dev/fb1`): `fb_ili9486`
- Touch controller: `ADS7846 Touchscreen` (`/dev/input/event1`)

Notes:

- This identifies controller/driver family, not exact seller brand/model name.
- The app uses framebuffer mode with `--fbdev /dev/fb1` by default.

## Setup on Raspberry Pi OS Lite

### 1) Install base packages

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git
```

### 2) Enable SPI

```bash
sudo raspi-config nonint do_spi 0
sudo reboot
```

### 3) Create venv and install dependencies

```bash
cd /home/eric/projects/digitalface
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run Manually

```bash
cd /home/eric/projects/digitalface
source .venv/bin/activate
python main.py --force-fb --fbdev /dev/fb1
```

If your display path differs, try `/dev/fb0`.

## Startup Script (Kill Old and Start New)

Use this script to stop existing `main.py` processes and start a clean instance:

```bash
cd /home/eric/projects/digitalface
./start_digitalface.sh
```

Optional framebuffer arg:

```bash
./start_digitalface.sh /dev/fb0
```

## Face Switching Scripts

### Set fixed face

```bash
./set_face.sh happy
./set_face.sh neutral
./set_face.sh listening
./set_face.sh surprised
```

### Auto mode (switch every 60 seconds by default)

```bash
./set_face.sh auto
```

Or specify interval seconds:

```bash
./set_face.sh auto 30
```

### List supported faces

```bash
./list_faces.sh
```

### Start/stop background cycle helper directly

```bash
./cycle_faces_bg.sh 60
./stop_cycle_faces.sh
```

## HMI Overlay System (LCD Messages)

Display messages, images, and alerts on the LCD via **Protocol v2** using Unix sockets.

### Quick Start

Send a message from Python:

```python
import socket
import json

payload = {
    "id": "msg-001",
    "type": "text",
    "text": "Hello World",
    "duration": 10,
    "font_size": 80,
    "priority": "normal",
    "animation": "none"
}

sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
sock.sendto(json.dumps(payload).encode(), "/home/eric/projects/digitalface/.runtime/digitalface_hmi.sock")
```

### Send from Command Line

Use the trigger-lcd tool from aireminder:

```bash
cd /home/eric/projects/aireminder/mcp/python
./trigger-lcd show "Your message here" -d 10
./trigger-lcd show "Big text" --font-size 80 -d 10
./trigger-lcd show "With animation" --animation fade_in -d 10
./trigger-lcd dismiss <message-id>
./trigger-lcd dismiss-all
```

### Protocol Documentation

See [PROTOCOL.md](PROTOCOL.md) for complete socket message format, field descriptions, animation types, and examples.

## Systemd Autostart (Recommended)

### 1) Disable fbcp autostart if present

```bash
grep -n 'fbcp' /etc/rc.local
sudo sed -i 's/^fbcp \&$/# fbcp disabled for digitalface/' /etc/rc.local
sudo pkill fbcp || true
```

### 2) Create service

```bash
sudo tee /etc/systemd/system/digitalface.service > /dev/null << 'SERVICE'
[Unit]
Description=Digital Face LCD Display
After=local-fs.target

[Service]
Type=simple
User=eric
WorkingDirectory=/home/eric/projects/digitalface
Environment=SDL_AUDIODRIVER=dummy
ExecStart=/home/eric/projects/digitalface/.venv/bin/python /home/eric/projects/digitalface/main.py --force-fb --fbdev /dev/fb1
Restart=always
RestartSec=2
StandardInput=null

[Install]
WantedBy=multi-user.target
SERVICE
```

### 3) Enable/start service

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now digitalface.service
```

### 4) Verify

```bash
systemctl is-enabled digitalface.service
systemctl is-active digitalface.service
systemctl status digitalface.service --no-pager
```

## Useful Commands

```bash
sudo systemctl restart digitalface.service
sudo systemctl stop digitalface.service
journalctl -u digitalface.service -n 100 --no-pager
```

## Troubleshooting

### How to physically test touch input

If you touch the screen and want to confirm touch is really working, use one of these methods.

#### Method A: Quick raw event test (recommended)

Use the helper script:

```bash
cd /home/eric/projects/digitalface
./test_touch.sh
```

If auto-detection picks the wrong device, pass it explicitly:

```bash
./test_touch.sh /dev/input/event1
```

The script starts `evtest` and shows live touch events.

1) Find the touch event node (usually ADS7846):

```bash
for e in /dev/input/event*; do
  n=$(basename "$e")
  name=$(cat "/sys/class/input/$n/device/name" 2>/dev/null || true)
  printf "%s: %s\n" "$e" "$name"
done
```

2) Observe events while touching the panel (replace event index if needed):

```bash
sudo evtest /dev/input/event1
```

What to expect when touch works:

- You will see changing `EV_ABS` values (X/Y coordinates)
- You will see press/release events (`BTN_TOUCH`)

If nothing changes when touching, check wiring/driver/module.

#### Method B: Verify app-level touch wake behavior

The app now turns LED display off after 10 minutes only when both are true:

- no expression/display change
- no touch event

To test quickly:

1) Start app in framebuffer mode:

```bash
cd /home/eric/projects/digitalface
source .venv/bin/activate
python main.py --force-fb --fbdev /dev/fb1
```

2) Wait until screen sleeps by idle rule.

3) Touch the screen.

Expected behavior:

- Display LED wakes and animation resumes.

Tip:

- For rapid testing during development, temporarily reduce timeout in `main.py`:
  - change `IDLE_TIMEOUT_SECONDS = 10 * 60` to e.g. `30`
  - restore it to 10 minutes after validation.

### Backlight control notes (mhs35/tft35a)

Some 3.5 inch SPI overlays do not expose `/sys/class/backlight/*`.
For this device (`dtoverlay=mhs35`), the app now tries these in order:

- framebuffer blank ioctl (`FBIOBLANK`)
- LED-class brightness node (for example `/sys/class/leds/default-on`)
- GPIO fallback via `pinctrl` (default `GPIO18`)

Optional overrides:

- `DIGITALFACE_BACKLIGHT_SYSFS=/sys/class/backlight/<node>`
- `DIGITALFACE_BACKLIGHT_LED=<led-name>`
- `DIGITALFACE_BACKLIGHT_GPIO=<pin-number>`
- `DIGITALFACE_BACKLIGHT_GPIO=<pin1,pin2,...>` (comma or colon separated)
- `DIGITALFACE_BACKLIGHT_GPIO_ACTIVE_LOW=1` (if your board uses inverted logic)

If backlight control needs sysfs/gpio writes, run service with privileges that can access those nodes.

For LCDWiki MSP3520 specifically:

- The module interface table marks `LED` as pin `8` (backlight control, high=on).
- If your wiring maps that to Raspberry Pi physical pin `8`, use `GPIO14`:
  - `DIGITALFACE_BACKLIGHT_GPIO=14`
- If your board inverts logic, set:
  - `DIGITALFACE_BACKLIGHT_GPIO_ACTIVE_LOW=1`

### Terminal and face switching

- Ensure `fbcp` is disabled/stopped.
- Ensure only one face process is running:

```bash
pgrep -af '/home/eric/projects/digitalface/main.py'
```

### `.venv/bin/activate` returns exit 126

Use:

```bash
source .venv/bin/activate
```

or

```bash
. .venv/bin/activate
```

### No image / black screen

- Check framebuffer devices:

```bash
ls -l /dev/fb*
cat /sys/class/graphics/fb0/name
cat /sys/class/graphics/fb1/name
```

- Check display driver:

```bash
lsmod | grep -E 'fb_ili|fbtft'
```
