# Digital Face for Raspberry Pi 4 (3.5 inch SPI LCD)

This project displays an animated digital face on a Raspberry Pi SPI LCD.

It is designed for Raspberry Pi OS Lite and supports direct framebuffer output (best for headless or console-only setups).

## Project Location

- /home/eric/projects/digitalface

## What This Program Does

- Draws a simple animated face (eyes, mouth, blink)
- Supports expressions:
  - neutral
  - happy
  - listening
  - surprised
- Runs with pygame
- Can write directly to framebuffer for SPI LCDs

## Requirements

- Raspberry Pi 4
- 3.5 inch SPI LCD (framebuffer driver available)
- Raspberry Pi OS Lite
- Python 3.11+

## Quick Run (Already Installed Project)

```bash
cd /home/eric/projects/digitalface
source .venv/bin/activate
python main.py --force-fb --fbdev /dev/fb1
```

If your LCD is mirrored from fb0 with fbcp, use:

```bash
python main.py --force-fb --fbdev /dev/fb0
```

## Fresh Setup on Raspberry Pi OS Lite

### 1) Update OS and install packages

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git
```

### 2) Enable SPI

```bash
sudo raspi-config nonint do_spi 0
```

Reboot after enabling SPI:

```bash
sudo reboot
```

### 3) Get project files

If you already have the folder, skip this.

```bash
cd /home/eric/projects
# put your project here (git clone or copy files)
```

### 4) Create virtual environment and install dependencies

```bash
cd /home/eric/projects/digitalface
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 5) Detect framebuffer devices

```bash
ls -l /dev/fb*
cat /sys/class/graphics/fb0/name
cat /sys/class/graphics/fb1/name
```

Typical result for SPI LCD:
- fb0: BCM2708 FB
- fb1: fb_ili9486 (or similar SPI panel driver)

### 6) Test display

```bash
cd /home/eric/projects/digitalface
source .venv/bin/activate
python main.py --force-fb --fbdev /dev/fb1
```

If nothing appears, try `/dev/fb0`.

## Keep Face Displayed Constantly (Autostart)

Use a systemd service so the face runs at boot and is not tied to your terminal session.

### 1) Disable fbcp autostart (if present)

Check:

```bash
grep -n 'fbcp' /etc/rc.local
```

If you see `fbcp &`, comment it out:

```bash
sudo sed -i 's/^fbcp \&$/# fbcp disabled for digitalface/' /etc/rc.local
```

Stop running fbcp for current boot:

```bash
sudo pkill fbcp || true
```

### 2) Create digitalface service

```bash
sudo tee /etc/systemd/system/digitalface.service > /dev/null << 'SERVICE'
[Unit]
Description=Digital Face LCD Display
After=local-fs.target

[Service]
Type=simple
User=eric
WorkingDirectory=/home/eric/projects/digitalface
ExecStart=/home/eric/projects/digitalface/.venv/bin/python /home/eric/projects/digitalface/main.py --force-fb --fbdev /dev/fb1
Restart=always
RestartSec=2
StandardInput=null

[Install]
WantedBy=multi-user.target
SERVICE
```

### 3) Enable and start service

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

Start manually:

```bash
cd /home/eric/projects/digitalface
source .venv/bin/activate
python main.py --force-fb --fbdev /dev/fb1
```

Stop service:

```bash
sudo systemctl stop digitalface.service
```

Restart service:

```bash
sudo systemctl restart digitalface.service
```

View logs:

```bash
journalctl -u digitalface.service -n 100 --no-pager
```

## Troubleshooting

### Face and terminal keep switching

Cause:
- fbcp mirrors fb0 to LCD while terminal still writes to source framebuffer.

Fix:
- disable `fbcp` in `/etc/rc.local`
- stop current fbcp process: `sudo pkill fbcp`
- run digitalface as service on the correct fb device

### Command `.venv/bin/activate` returns permission denied (exit 126)

Use:

```bash
source .venv/bin/activate
```

or

```bash
. .venv/bin/activate
```

### Black screen

- test both framebuffer devices (`/dev/fb0`, `/dev/fb1`)
- verify user is in video group: `id`
- verify LCD driver is loaded: `lsmod | grep -E 'fb_ili|fbtft'`

### Service does not start

- check status and logs:

```bash
systemctl status digitalface.service --no-pager
journalctl -u digitalface.service -n 200 --no-pager
```

## Next Step

Add a small local API (socket or HTTP) so a speech listener can switch expressions automatically while you talk.
