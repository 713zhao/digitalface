#!/usr/bin/env python3
"""Application layer: face logic, text, icons, animations."""

import json
import math
import os
import time

import pygame

from driver.display_driver import DisplayDriver


THEMES = {
    "neutral": {
        "bg_top": (16, 20, 42),
        "bg_bottom": (5, 8, 18),
        "face": (70, 96, 152),
        "eye": (230, 242, 255),
        "pupil": (16, 24, 36),
        "mouth": (128, 222, 255),
        "accent": (86, 255, 214),
        "accent_2": (255, 208, 98),
        "label": "NEUTRAL",
    },
    "happy": {
        "bg_top": (28, 42, 76),
        "bg_bottom": (10, 14, 28),
        "face": (88, 112, 166),
        "eye": (246, 248, 255),
        "pupil": (24, 28, 40),
        "mouth": (255, 205, 96),
        "accent": (88, 255, 190),
        "accent_2": (255, 110, 164),
        "label": "HAPPY",
    },
    "listening": {
        "bg_top": (9, 40, 64),
        "bg_bottom": (4, 12, 22),
        "face": (52, 118, 144),
        "eye": (220, 247, 255),
        "pupil": (14, 30, 40),
        "mouth": (116, 246, 255),
        "accent": (0, 255, 200),
        "accent_2": (110, 176, 255),
        "label": "LISTENING",
    },
    "surprised": {
        "bg_top": (46, 30, 72),
        "bg_bottom": (14, 10, 26),
        "face": (102, 80, 156),
        "eye": (244, 238, 255),
        "pupil": (36, 20, 52),
        "mouth": (255, 134, 142),
        "accent": (255, 96, 164),
        "accent_2": (130, 220, 255),
        "label": "SURPRISED",
    },
}
EXPRESSION_ORDER = ["happy", "neutral", "listening", "surprised"]


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


class FaceApplication:
    def __init__(self, driver: DisplayDriver, control_file: str, default_expression: str = "happy", pause_file: str | None = None, hmi_request_file: str | None = None, hmi_default_duration: float = 10.0) -> None:
        self.driver = driver
        self.control_file = control_file
        self.pause_file = pause_file
        self.expression = default_expression
        self._display_changed = True
        self.blink_closed_until = 0.0
        self.next_blink_at = time.time() + 2.2
        self.next_control_poll_at = 0.0
        self.bg_cache = {}
        self.hmi_request_file = hmi_request_file
        self.hmi_default_duration = hmi_default_duration
        self.hmi_text: str | None = None
        self.hmi_until: float = 0.0
        self.hmi_duration: float = 0.0
        self.hmi_repeat: bool = False
        self.hmi_repeat_interval: float = 60.0
        self.hmi_next_repeat_at: float = 0.0
        self._hmi_queue: list[dict] = []
        self.next_hmi_poll_at: float = 0.0
        self._hmi_font: pygame.font.Font | None = None

    def set_expression(self, name: str) -> None:
        if name in THEMES:
            if name != self.expression:
                self._display_changed = True
            self.expression = name

    def consume_display_changed(self) -> bool:
        changed = self._display_changed
        self._display_changed = False
        return changed

    def cycle_to_next_expression(self) -> None:
        try:
            idx = EXPRESSION_ORDER.index(self.expression)
        except ValueError:
            idx = 0
        next_idx = (idx + 1) % len(EXPRESSION_ORDER)
        self.set_expression(EXPRESSION_ORDER[next_idx])

    def update(self, now: float) -> None:
        if now >= self.next_control_poll_at:
            self._poll_external_expression(now)
            self.next_control_poll_at = now + 0.35

        if now >= self.next_hmi_poll_at:
            self._poll_hmi_request(now)
            self.next_hmi_poll_at = now + 0.1

        if self.hmi_text is not None and now >= self.hmi_until:
            if self.hmi_repeat:
                if self.hmi_next_repeat_at == 0.0:
                    # just finished showing — schedule next repeat
                    self.hmi_next_repeat_at = now + self.hmi_repeat_interval
                elif now >= self.hmi_next_repeat_at:
                    # repeat fires — show again
                    self.hmi_until = now + self.hmi_duration
                    self.hmi_next_repeat_at = 0.0
                    self._display_changed = True
            else:
                self.hmi_text = None
                self._display_changed = True
                self._dequeue_hmi(now)

        if now >= self.next_blink_at:
            self.blink_closed_until = now + 0.10
            self.next_blink_at = now + 2.0 + (math.sin(now) + 1.0) * 0.4

    def render(self, now: float) -> None:
        if self.hmi_text is not None and now < self.hmi_until:
            self._render_hmi_overlay(now)
            return

        theme = THEMES.get(self.expression, THEMES["happy"])
        self.driver.blit(self._get_background(self.expression), (0, 0))

        cx = self.driver.width // 2
        cy = self.driver.height // 2 - 2

        pulse = (math.sin(now * 2.2) + 1.0) * 0.5
        aura_radius = int(112 + pulse * 10)
        self.driver.circle(theme["accent"], (cx, cy), aura_radius, 2)

        head_rect = (86, 36, self.driver.width - 172, self.driver.height - 100)
        self.driver.ellipse(theme["face"], head_rect)
        self.driver.ellipse(theme["accent"], head_rect, 3)

        ear_y = cy - 36
        self.driver.circle(theme["face"], (cx - 126, ear_y), 22)
        self.driver.circle(theme["face"], (cx + 126, ear_y), 22)
        self.driver.circle(theme["accent_2"], (cx - 126, ear_y), 10)
        self.driver.circle(theme["accent_2"], (cx + 126, ear_y), 10)

        self._draw_eyes(cx, cy, now, theme)
        self._draw_mouth(cx, cy, theme)

    def dismiss_hmi(self) -> None:
        """Dismiss any active HMI overlay (called on user touch)."""
        if self.hmi_text is not None:
            self.hmi_text = None
            self.hmi_repeat = False
            self.hmi_next_repeat_at = 0.0
            self._display_changed = True
            self._dequeue_hmi(time.time())

    def _dequeue_hmi(self, now: float) -> None:
        """Pop the next queued HMI item and start displaying it."""
        if not self._hmi_queue:
            return
        item = self._hmi_queue.pop(0)
        self.hmi_text = item["text"]
        self.hmi_duration = item["duration"]
        self.hmi_until = now + item["duration"]
        self.hmi_repeat = item["repeat"]
        self.hmi_repeat_interval = item["repeat_interval"]
        self.hmi_next_repeat_at = 0.0
        self._display_changed = True

    def _poll_hmi_request(self, now: float) -> None:
        if not self.hmi_request_file:
            return
        try:
            with open(self.hmi_request_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
            os.unlink(self.hmi_request_file)
        except (FileNotFoundError, OSError):
            return
        try:
            data = json.loads(content)
        except (ValueError, TypeError):
            return
        text = str(data.get("text", "")).strip()
        if not text:
            return
        try:
            duration = float(data.get("duration") or self.hmi_default_duration)
        except (TypeError, ValueError):
            duration = self.hmi_default_duration
        repeat_val = data.get("repeat")
        repeat = False
        repeat_interval = 60.0
        if repeat_val not in (None, False, 0):
            repeat = True
            if isinstance(repeat_val, (int, float)) and repeat_val is not True:
                repeat_interval = max(5.0, float(repeat_val))
        self._hmi_queue.append({
            "text": text,
            "duration": max(1.0, duration),
            "repeat": repeat,
            "repeat_interval": repeat_interval,
        })
        # Start immediately only if nothing is currently showing
        if self.hmi_text is None:
            self._dequeue_hmi(now)

    def _get_hmi_font(self) -> pygame.font.Font:
        if self._hmi_font is None:
            self._hmi_font = pygame.font.Font(None, 36)
        return self._hmi_font

    def _wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        lines: list[str] = []
        for paragraph in text.splitlines():
            words = paragraph.split()
            if not words:
                lines.append("")
                continue
            current = ""
            for word in words:
                test = (current + " " + word).strip()
                if font.size(test)[0] <= max_width:
                    current = test
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)
        return lines

    def _render_hmi_overlay(self, now: float) -> None:
        W, H = self.driver.width, self.driver.height
        self.driver.fill((10, 12, 22))

        padding = 16
        panel_rect = (padding, padding, W - 2 * padding, H - 2 * padding)
        self.driver.rect((22, 28, 52), panel_rect)
        self.driver.rect((80, 130, 210), panel_rect, 2)

        font = self._get_hmi_font()
        text_margin = 20
        wrap_width = W - 2 * padding - 2 * text_margin
        lines = self._wrap_text(self.hmi_text or "", font, wrap_width)
        line_h = font.get_linesize()
        total_h = line_h * len(lines)
        start_y = padding + (H - 2 * padding - total_h) // 2

        for i, line in enumerate(lines):
            lw, _ = font.size(line)
            x = (W - lw) // 2
            y = start_y + i * line_h
            self.driver.text(line, (220, 238, 255), (x, y), font=font)

        remaining = max(0.0, self.hmi_until - now)
        frac = remaining / self.hmi_duration if self.hmi_duration > 0 else 0.0
        bar_y = H - padding - 12
        bar_x = padding + text_margin
        bar_w = W - 2 * padding - 2 * text_margin
        self.driver.rect((35, 45, 75), (bar_x, bar_y, bar_w, 6))
        if frac > 0:
            self.driver.rect((80, 130, 210), (bar_x, bar_y, int(bar_w * frac), 6))

    def _poll_external_expression(self, now: float) -> None:
        if self.pause_file:
            try:
                with open(self.pause_file, "r", encoding="utf-8") as f:
                    pause_until = float(f.read().strip())
                if now < pause_until:
                    return
            except (FileNotFoundError, OSError, ValueError):
                pass

        try:
            with open(self.control_file, "r", encoding="utf-8") as f:
                requested = f.read().strip().lower()
        except FileNotFoundError:
            return
        except OSError:
            return

        if requested in THEMES and requested != self.expression:
            self.set_expression(requested)

    def _draw_vertical_gradient(self, top: tuple[int, int, int], bottom: tuple[int, int, int], surface) -> None:
        for y in range(self.driver.height):
            t = y / (self.driver.height - 1)
            color = (_lerp(top[0], bottom[0], t), _lerp(top[1], bottom[1], t), _lerp(top[2], bottom[2], t))
            self.driver.line(color, (0, y), (self.driver.width, y), 1, surface)

    def _draw_soft_circle(self, center: tuple[int, int], radius: int, color: tuple[int, int, int], alpha: int, surface) -> None:
        glow = self.driver.create_surface()
        for ring in range(radius, 0, -8):
            ring_alpha = max(0, int(alpha * (ring / radius) ** 2))
            self.driver.circle((*color, ring_alpha), center, ring, 0, glow)
        self.driver.blit(glow, (0, 0), surface)

    def _build_background(self, expr: str):
        theme = THEMES[expr]
        bg = self.driver.create_surface()
        self._draw_vertical_gradient(theme["bg_top"], theme["bg_bottom"], bg)

        cx = self.driver.width // 2
        self._draw_soft_circle((cx - 130, 68), 88, theme["accent"], 72, bg)
        self._draw_soft_circle((cx + 148, 84), 76, theme["accent_2"], 70, bg)

        strip = (0, self.driver.height - 34, self.driver.width, 34)
        self.driver.rect((10, 12, 20), strip, 0, bg)
        self.driver.line(theme["accent"], (0, self.driver.height - 34), (self.driver.width, self.driver.height - 34), 2, bg)
        self.driver.circle(theme["accent"], (16, self.driver.height - 17), 4, 0, bg)
        self.driver.text(theme["label"], (232, 240, 255), (30, self.driver.height - 25), surface=bg)
        return bg

    def _get_background(self, expr: str):
        if expr not in self.bg_cache:
            self.bg_cache[expr] = self._build_background(expr)
        return self.bg_cache[expr]

    def _draw_eyes(self, cx: int, cy: int, now: float, theme: dict) -> None:
        eye_y = cy - 44
        eye_dx = 76
        eye_w = 74
        eye_h = 52

        blink = time.time() <= self.blink_closed_until
        if blink:
            self.driver.line(theme["eye"], (cx - eye_dx - 30, eye_y), (cx - eye_dx + 30, eye_y), 6)
            self.driver.line(theme["eye"], (cx + eye_dx - 30, eye_y), (cx + eye_dx + 30, eye_y), 6)
            return

        self.driver.ellipse(theme["eye"], (cx - eye_dx - eye_w // 2, eye_y - eye_h // 2, eye_w, eye_h))
        self.driver.ellipse(theme["eye"], (cx + eye_dx - eye_w // 2, eye_y - eye_h // 2, eye_w, eye_h))

        if self.expression == "listening":
            offset_x = int(math.sin(now * 2.8) * 7)
            offset_y = int(math.cos(now * 2.2) * 3)
        elif self.expression == "surprised":
            offset_x = 0
            offset_y = -1
        else:
            offset_x = int(math.sin(now * 1.0) * 2)
            offset_y = int(math.cos(now * 0.8) * 2)

        pupil_r = 8 if self.expression == "surprised" else 11
        self.driver.circle(theme["pupil"], (cx - eye_dx + offset_x, eye_y + offset_y), pupil_r)
        self.driver.circle(theme["pupil"], (cx + eye_dx + offset_x, eye_y + offset_y), pupil_r)
        self.driver.circle((255, 255, 255), (cx - eye_dx + offset_x - 3, eye_y + offset_y - 4), 2)
        self.driver.circle((255, 255, 255), (cx + eye_dx + offset_x - 3, eye_y + offset_y - 4), 2)

    def _draw_mouth(self, cx: int, cy: int, theme: dict) -> None:
        if self.expression == "happy":
            self.driver.arc(theme["mouth"], (cx - 74, cy + 0, 148, 88), 3.25, 6.17, 7)
        elif self.expression == "surprised":
            self.driver.circle(theme["mouth"], (cx, cy + 64), 22, 6)
        elif self.expression == "listening":
            self.driver.arc(theme["mouth"], (cx - 64, cy + 17, 128, 34), 3.14, 6.28, 6)
        else:
            self.driver.line(theme["mouth"], (cx - 52, cy + 60), (cx + 52, cy + 60), 6)
