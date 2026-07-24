#!/usr/bin/env python3
"""Interactive ADS7846/XPT2046 touch calibration.
Run as root (or with access to /dev/input/event*).
Stop digitalface service before running.
"""
import os
import struct
import time
import glob
import select

EVENT_FMT = "llHHi"
EVENT_SIZE = struct.calcsize(EVENT_FMT)
EV_ABS = 3
EV_SYN = 0
ABS_X = 0
ABS_Y = 1


def find_touch_device():
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            with open(f"/sys/class/input/{os.path.basename(path)}/device/name") as f:
                name = f.read().strip()
            if any(k in name.lower() for k in ("ads7846", "xpt2046", "touch", "touchscreen")):
                return path, name
        except OSError:
            pass
    # fallback: try event1
    return "/dev/input/event1", "unknown"


def collect_corner(fd, label):
    print(f"\n{'='*50}")
    print(f"  Touch the {label} corner repeatedly.")
    print(f"  Press ENTER when done.")
    print(f"{'='*50}")

    xs, ys = [], []
    cur_x, cur_y = -1, -1

    import threading
    enter_pressed = threading.Event()

    def wait_enter():
        input()
        enter_pressed.set()

    t = threading.Thread(target=wait_enter, daemon=True)
    t.start()

    while not enter_pressed.is_set():
        r, _, _ = select.select([fd], [], [], 0.05)
        if not r:
            continue
        data = os.read(fd, EVENT_SIZE)
        if len(data) < EVENT_SIZE:
            continue
        _, _, ev_type, code, value = struct.unpack(EVENT_FMT, data)
        if ev_type == EV_ABS and code == ABS_X:
            cur_x = value
        elif ev_type == EV_ABS and code == ABS_Y:
            cur_y = value
        elif ev_type == EV_SYN and cur_x >= 0 and cur_y >= 0:
            xs.append(cur_x)
            ys.append(cur_y)
            print(f"  sample {len(xs):3d}: raw_x={cur_x:5d}  raw_y={cur_y:5d}", flush=True)
            cur_x, cur_y = -1, -1

    if not xs:
        print("  No samples collected!")
        return None, None

    avg_x = int(sum(xs) / len(xs))
    avg_y = int(sum(ys) / len(ys))
    print(f"  → average: raw_x={avg_x}  raw_y={avg_y}  ({len(xs)} samples)")
    return avg_x, avg_y


def main():
    dev, name = find_touch_device()
    print(f"Using device: {dev} ({name})")

    try:
        fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
    except PermissionError:
        print(f"ERROR: cannot open {dev}. Try: sudo python3 calibrate_touch.py")
        return

    corners = {}
    for label in ["TOP-LEFT", "TOP-RIGHT", "BOTTOM-LEFT", "BOTTOM-RIGHT"]:
        ax, ay = collect_corner(fd, label)
        if ax is None:
            print(f"Skipped {label}")
        else:
            corners[label] = (ax, ay)

    os.close(fd)

    print("\n" + "="*50)
    print("CALIBRATION RESULTS")
    print("="*50)
    for label, (x, y) in corners.items():
        print(f"  {label:15s}: raw_x={x:5d}  raw_y={y:5d}")

    # Derive constants
    # X: left edge = min(TL_x, BL_x), right edge = max(TR_x, BR_x)
    # Y: top edge and bottom edge — figure out which raw value is larger
    tl = corners.get("TOP-LEFT")
    tr = corners.get("TOP-RIGHT")
    bl = corners.get("BOTTOM-LEFT")
    br = corners.get("BOTTOM-RIGHT")

    if tl and br and tr and bl:
        x_min = min(tl[0], bl[0])
        x_max = max(tr[0], br[0])
        # For Y: take top average and bottom average (may be inverted)
        y_top = (tl[1] + tr[1]) // 2
        y_bot = (bl[1] + br[1]) // 2
        print(f"\nDerived calibration:")
        print(f"  TOUCH_X_MIN = {x_min}")
        print(f"  TOUCH_X_MAX = {x_max}")
        print(f"  TOUCH_Y_MIN = {y_top}   # raw value at physical TOP")
        print(f"  TOUCH_Y_MAX = {y_bot}   # raw value at physical BOTTOM")
        inv = "YES (y_min > y_max)" if y_top > y_bot else "NO (y_min < y_max)"
        print(f"  Y axis inverted: {inv}")
        print()
        print("Paste these into main.py:")
        print(f"  TOUCH_X_MIN = {x_min}")
        print(f"  TOUCH_X_MAX = {x_max}")
        print(f"  TOUCH_Y_MIN = {y_top}")
        print(f"  TOUCH_Y_MAX = {y_bot}")
        print(f"  TOUCH_ROTATE_180 = True")


if __name__ == "__main__":
    main()
