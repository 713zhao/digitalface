#!/usr/bin/env python3
"""Display driver layer: drawing interfaces + presenters (SDL/fb)."""

import glob
import fcntl
import os
import shutil
import struct
import subprocess
import pygame

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


class BacklightController:
    def __init__(self, devices: list[str] | None = None) -> None:
        self.devices = devices or self._discover_backlight_devices()
        self._saved_brightness: dict[str, int] = {}
        self.gpio_pins = self._discover_backlight_gpio_pins()
        self.gpio_active_low = os.environ.get("DIGITALFACE_BACKLIGHT_GPIO_ACTIVE_LOW", "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

    @staticmethod
    def _discover_backlight_devices() -> list[str]:
        discovered: list[str] = []

        override = os.environ.get("DIGITALFACE_BACKLIGHT_SYSFS", "").strip()
        if override:
            for path in override.split(":"):
                path = path.strip()
                if path and os.path.isdir(path):
                    discovered.append(path)
            if discovered:
                return discovered

        discovered.extend(sorted(glob.glob("/sys/class/backlight/*")))

        led_override = os.environ.get("DIGITALFACE_BACKLIGHT_LED", "").strip()
        if led_override:
            for led in led_override.split(":"):
                led = led.strip()
                if not led:
                    continue
                path = f"/sys/class/leds/{led}"
                if os.path.isdir(path):
                    discovered.append(path)

        # mhs35/tft35a setups often expose panel backlight as "default-on" LED.
        has_tft35a = os.path.exists("/sys/firmware/devicetree/base/soc/spi@7e204000/tft35a@0")
        default_on = "/sys/class/leds/default-on"
        if has_tft35a and os.path.isdir(default_on):
            discovered.append(default_on)

        for led_path in sorted(glob.glob("/sys/class/leds/*")):
            name = os.path.basename(led_path).lower()
            if name in ("act", "pwr", "mmc0", "mmc0::"):
                continue
            if not any(k in name for k in ("backlight", "lcd", "tft", "default-on")):
                continue
            discovered.append(led_path)

        unique: list[str] = []
        seen = set()
        for path in discovered:
            if path in seen:
                continue
            if os.path.isdir(path):
                unique.append(path)
                seen.add(path)
        return unique

    @staticmethod
    def _discover_backlight_gpio_pins() -> list[int]:
        pin_override = os.environ.get("DIGITALFACE_BACKLIGHT_GPIO", "").strip()
        if pin_override:
            pins: list[int] = []
            for part in pin_override.replace(":", ",").split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    pins.append(int(part))
                except ValueError:
                    continue
            return pins

        has_tft35a = os.path.exists("/sys/firmware/devicetree/base/soc/spi@7e204000/tft35a@0")
        if has_tft35a:
            # Common backlight pin on many 3.5" SPI TFT boards.
            return [18]
        return []

    def _read_int(self, path: str) -> int | None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            return None

    def _write_int(self, path: str, value: int) -> bool:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(str(value))
            return True
        except OSError:
            return False

    def set_enabled(self, enabled: bool) -> bool:
        changed_any = False
        for dev in self.devices:
            brightness_path = os.path.join(dev, "brightness")
            max_path = os.path.join(dev, "max_brightness")
            bl_power_path = os.path.join(dev, "bl_power")

            if enabled:
                saved = self._saved_brightness.get(dev)
                if saved is None or saved <= 0:
                    saved = self._read_int(max_path) or 1

                # Some backlight drivers honor bl_power while others only brightness.
                if os.path.exists(bl_power_path):
                    changed_any = self._write_int(bl_power_path, 0) or changed_any
                if os.path.exists(brightness_path):
                    changed_any = self._write_int(brightness_path, max(1, saved)) or changed_any
            else:
                current = self._read_int(brightness_path)
                if current is not None and current > 0:
                    self._saved_brightness[dev] = current

                if os.path.exists(brightness_path):
                    changed_any = self._write_int(brightness_path, 0) or changed_any
                if os.path.exists(bl_power_path):
                    # 4 is the standardized "power down" value.
                    changed_any = self._write_int(bl_power_path, 4) or changed_any

        if self.gpio_pins:
            changed_any = self._set_gpio_backlight(enabled) or changed_any

        return changed_any

    def _set_gpio_backlight(self, enabled: bool) -> bool:
        if not self.gpio_pins:
            return False
        if shutil.which("pinctrl") is None:
            return False

        target_high = enabled
        if self.gpio_active_low:
            target_high = not target_high

        level = "dh" if target_high else "dl"
        changed_any = False
        for pin in self.gpio_pins:
            try:
                subprocess.run(
                    ["pinctrl", "set", str(pin), "op", level],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                changed_any = True
            except (OSError, subprocess.CalledProcessError):
                continue
        return changed_any


class TouchDriver:
    EVENT_STRUCT = struct.Struct("llHHi")
    EV_KEY = 0x01
    EV_ABS = 0x03
    BTN_TOUCH = 0x014A
    ABS_X = 0x00
    ABS_Y = 0x01
    ABS_MT_POSITION_X = 0x35
    ABS_MT_POSITION_Y = 0x36
    ABS_PRESSURE = 0x18
    DEFAULT_KEYWORDS = ("touch", "tsc", "goodix", "ft5", "xpt2046", "ads7846")

    def __init__(self, event_paths: list[str] | None = None) -> None:
        self._fds: list[int] = []
        self.event_paths = event_paths if event_paths is not None else self._autodetect_touch_events()

        for path in self.event_paths:
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            self._fds.append(fd)

    @staticmethod
    def _autodetect_touch_events() -> list[str]:
        override = os.environ.get("DIGITALFACE_TOUCHDEV", "").strip()
        if override:
            return [p for p in override.split(":") if p]

        touch_events: list[str] = []
        for path in sorted(glob.glob("/dev/input/event*")):
            event_name = os.path.basename(path)
            sys_name_path = f"/sys/class/input/{event_name}/device/name"
            try:
                with open(sys_name_path, "r", encoding="utf-8") as f:
                    device_name = f.read().strip().lower()
            except OSError:
                continue

            if any(keyword in device_name for keyword in TouchDriver.DEFAULT_KEYWORDS):
                touch_events.append(path)

        return touch_events

    def poll(self) -> bool:
        touched = False
        size = self.EVENT_STRUCT.size

        for fd in self._fds:
            while True:
                try:
                    data = os.read(fd, size)
                except BlockingIOError:
                    break
                except OSError:
                    break

                if len(data) < size:
                    break

                _sec, _usec, ev_type, code, value = self.EVENT_STRUCT.unpack(data)
                if ev_type == self.EV_KEY and code == self.BTN_TOUCH and value == 1:
                    touched = True
                elif ev_type == self.EV_ABS and code == self.ABS_PRESSURE and value > 0:
                    touched = True

        return touched

    def close(self) -> None:
        for fd in self._fds:
            try:
                os.close(fd)
            except OSError:
                pass
        self._fds.clear()


class FramebufferPresenter:
    FBIOBLANK = 0x4611
    FB_BLANK_UNBLANK = 0
    FB_BLANK_POWERDOWN = 4

    def __init__(self, fbdev: str, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.fd = os.open(fbdev, os.O_RDWR)
        self.frame = bytearray(width * height * 2)
        self.backlight = BacklightController()
        self.led_enabled = True

    def present(self, surface: pygame.Surface) -> None:
        self.present_rows(surface, 0, self.height)

    def present_rows(self, surface: pygame.Surface, y_start: int, y_end: int) -> None:
        """Write only rows y_start..y_end (exclusive) to the framebuffer."""
        h = y_end - y_start
        if h <= 0:
            return
        if y_start == 0 and y_end == self.height:
            rgb = pygame.image.tostring(surface, "RGB")
        else:
            rgb = pygame.image.tostring(surface.subsurface((0, y_start, self.width, h)), "RGB")
        if _HAS_NUMPY:
            arr = np.frombuffer(rgb, dtype=np.uint8).reshape(-1, 3)
            r = arr[:, 0].astype(np.uint16)
            g = arr[:, 1].astype(np.uint16)
            b = arr[:, 2].astype(np.uint16)
            data = (((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)).astype('<u2').tobytes()
        else:
            src = memoryview(rgb)
            dst = bytearray(h * self.width * 2)
            j = 0
            for i in range(0, len(src), 3):
                val = ((src[i] & 0xF8) << 8) | ((src[i+1] & 0xFC) << 3) | (src[i+2] >> 3)
                dst[j] = val & 0xFF
                dst[j+1] = (val >> 8) & 0xFF
                j += 2
            data = bytes(dst)
        os.lseek(self.fd, y_start * self.width * 2, os.SEEK_SET)
        os.write(self.fd, data)

    def close(self) -> None:
        os.close(self.fd)

    def set_led_enabled(self, enabled: bool) -> bool:
        changed = self.backlight.set_enabled(enabled)
        try:
            level = self.FB_BLANK_UNBLANK if enabled else self.FB_BLANK_POWERDOWN
            fcntl.ioctl(self.fd, self.FBIOBLANK, level)
            changed = True
        except OSError:
            # Some framebuffer drivers don't support FBIOBLANK; fallback to black frame.
            if not enabled:
                self.frame[:] = b"\x00" * len(self.frame)
                os.lseek(self.fd, 0, os.SEEK_SET)
                os.write(self.fd, self.frame)
                changed = True
        self.led_enabled = enabled
        return changed


class SDLPresenter:
    def present(self, _surface: pygame.Surface) -> None:
        pygame.display.flip()

    def close(self) -> None:
        pygame.quit()

    def set_led_enabled(self, _enabled: bool) -> bool:
        return True


class DisplayDriver:
    def __init__(self, surface: pygame.Surface, presenter, width: int, height: int, rotate_180: bool = False) -> None:
        self.surface = surface
        self.presenter = presenter
        self.width = width
        self.height = height
        self.rotate_180 = rotate_180
        self.default_font = pygame.font.Font(None, 24)
        self.led_enabled = True

    def create_surface(self) -> pygame.Surface:
        return pygame.Surface((self.width, self.height), pygame.SRCALPHA)

    def fill(self, color: tuple[int, int, int], surface: pygame.Surface | None = None) -> None:
        (surface or self.surface).fill(color)

    def blit(self, source: pygame.Surface, pos: tuple[int, int], surface: pygame.Surface | None = None) -> None:
        (surface or self.surface).blit(source, pos)

    def line(self, color: tuple[int, int, int], start: tuple[int, int], end: tuple[int, int], width: int = 1, surface: pygame.Surface | None = None) -> None:
        pygame.draw.line(surface or self.surface, color, start, end, width)

    def rect(self, color: tuple[int, int, int], rect: pygame.Rect, width: int = 0, surface: pygame.Surface | None = None) -> None:
        pygame.draw.rect(surface or self.surface, color, rect, width)

    def circle(self, color: tuple[int, int, int], center: tuple[int, int], radius: int, width: int = 0, surface: pygame.Surface | None = None) -> None:
        pygame.draw.circle(surface or self.surface, color, center, radius, width)

    def ellipse(self, color: tuple[int, int, int], rect: pygame.Rect, width: int = 0, surface: pygame.Surface | None = None) -> None:
        pygame.draw.ellipse(surface or self.surface, color, rect, width)

    def arc(self, color: tuple[int, int, int], rect: tuple[int, int, int, int], start_angle: float, end_angle: float, width: int, surface: pygame.Surface | None = None) -> None:
        pygame.draw.arc(surface or self.surface, color, rect, start_angle, end_angle, width)

    def text(self, text: str, color: tuple[int, int, int], pos: tuple[int, int], font: pygame.font.Font | None = None, surface: pygame.Surface | None = None) -> None:
        use_font = font or self.default_font
        rendered = use_font.render(text, True, color)
        (surface or self.surface).blit(rendered, pos)

    def present(self) -> None:
        if self.rotate_180:
            self.presenter.present(pygame.transform.flip(self.surface, True, True))
            return
        self.presenter.present(self.surface)

    def present_rows(self, y_start: int, y_end: int) -> None:
        """Write only rows y_start..y_end (exclusive), handling 180° rotation."""
        if not hasattr(self.presenter, "present_rows"):
            self.present()
            return
        if self.rotate_180:
            # After flip: original row y → physical row (height-1-y)
            # original rows y_start..y_end → physical rows (height-y_end)..(height-y_start)
            flipped = pygame.transform.flip(self.surface, True, True)
            self.presenter.present_rows(flipped, self.height - y_end, self.height - y_start)
        else:
            self.presenter.present_rows(self.surface, y_start, y_end)

    def set_led_enabled(self, enabled: bool) -> bool:
        changed = False
        if hasattr(self.presenter, "set_led_enabled"):
            changed = bool(self.presenter.set_led_enabled(enabled))
        self.led_enabled = enabled
        return changed

    def close(self) -> None:
        self.presenter.close()


def create_sdl_driver(width: int, height: int, rotate_180: bool = False) -> DisplayDriver:
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_caption("Digital Face")
    surface = pygame.display.set_mode((width, height), pygame.FULLSCREEN)
    return DisplayDriver(surface, SDLPresenter(), width, height, rotate_180=rotate_180)


def create_framebuffer_driver(fbdev: str, width: int, height: int, rotate_180: bool = False) -> DisplayDriver:
    pygame.font.init()
    surface = pygame.Surface((width, height))
    presenter = FramebufferPresenter(fbdev, width, height)
    return DisplayDriver(surface, presenter, width, height, rotate_180=rotate_180)


def create_touch_driver(touchdevs: list[str] | None = None) -> TouchDriver:
    return TouchDriver(touchdevs)
