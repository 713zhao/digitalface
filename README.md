# Digital Face for Raspberry Pi 4 (3.5 inch SPI LCD)

A colorful animated digital face for Raspberry Pi OS Lite + SPI LCD.

## Project Path

- /home/eric/projects/digitalface

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

## Requirements

- Raspberry Pi 4
- 3.5 inch SPI LCD with framebuffer driver
- Raspberry Pi OS Lite
- Python 3.11+

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
