#!/usr/bin/env python3
"""Application layer: face logic, text, icons, animations."""

import json
import math
import os
import socket
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
    def __init__(self, driver: DisplayDriver, control_file: str, default_expression: str = "happy", pause_file: str | None = None, hmi_request_file: str | None = None, hmi_socket_file: str | None = None, hmi_default_duration: float = 10.0) -> None:
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
        self.hmi_socket_file = hmi_socket_file
        self.hmi_default_duration = hmi_default_duration
        self.hmi_text: str | None = None
        self.hmi_until: float = 0.0
        self.hmi_duration: float = 0.0
        self.hmi_repeat: bool = False
        self.hmi_repeat_interval: float = 60.0
        self.hmi_next_repeat_at: float = 0.0
        self.hmi_persistent: bool = False
        self.hmi_type: str = "text"
        self.hmi_image_path: str | None = None
        self.hmi_font_size: int = 80
        self.hmi_animation: str = "none"
        self.hmi_animation_duration: float = 0.5
        self.hmi_animation_start: float = 0.0
        self.hmi_scroll_offset: float = 0.0
        self.hmi_needs_scroll: bool = False
        self._hmi_queue: list[dict] = []
        self.next_hmi_poll_at: float = 0.0
        self._hmi_font: pygame.font.Font | None = None
        self._hmi_font_size: int = 80
        self._hmi_image_cache: dict[str, pygame.Surface] = {}
        self._hmi_socket: socket.socket | None = None
        # Protocol v2: track messages by ID
        self._hmi_current_id: str | None = None
        self._hmi_active_messages: dict[str, dict] = {}  # id -> message data
        self._init_hmi_socket()

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

        if self.hmi_text is not None and now >= self.hmi_until and not self.hmi_persistent:
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
                if self._hmi_current_id:
                    self._hmi_active_messages.pop(self._hmi_current_id, None)
                self.hmi_text = None
                self._hmi_current_id = None
                self._display_changed = True
                self._dequeue_hmi(now)

        if now >= self.next_blink_at:
            self.blink_closed_until = now + 0.10
            self.next_blink_at = now + 2.0 + (math.sin(now) + 1.0) * 0.4

    def render(self, now: float) -> None:
        if self.hmi_text is not None and (now < self.hmi_until or self.hmi_persistent):
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

    def close(self) -> None:
        sock = self._hmi_socket
        self._hmi_socket = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def _init_hmi_socket(self) -> None:
        if not self.hmi_socket_file:
            return
        try:
            os.makedirs(os.path.dirname(self.hmi_socket_file), exist_ok=True)
        except OSError:
            return
        try:
            if os.path.exists(self.hmi_socket_file):
                os.unlink(self.hmi_socket_file)
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            sock.bind(self.hmi_socket_file)
            # Make socket world-writable for multi-user access (root server, eric client)
            os.chmod(self.hmi_socket_file, 0o666)
            sock.setblocking(False)
            self._hmi_socket = sock
        except OSError:
            self._hmi_socket = None

    def _enqueue_hmi_data(self, data: dict, now: float) -> None:
        """Process incoming HMI message (Protocol v2)."""
        # Handle dismiss command
        if data.get("dismiss"):
            dismiss_target = data.get("dismiss")
            if dismiss_target is True:
                # Dismiss all
                self.hmi_text = None
                self.hmi_repeat = False
                self.hmi_next_repeat_at = 0.0
                self.hmi_persistent = False
                self._hmi_queue.clear()
                self._hmi_current_id = None
                self._hmi_active_messages.clear()
                self._display_changed = True
            elif isinstance(dismiss_target, str):
                # Dismiss specific ID
                if dismiss_target in self._hmi_active_messages:
                    del self._hmi_active_messages[dismiss_target]
                self._hmi_queue = [
                    item for item in self._hmi_queue if item.get("id") != dismiss_target
                ]
                if self._hmi_current_id == dismiss_target:
                    # Currently showing this message, dequeue it
                    self.hmi_text = None
                    self.hmi_until = 0.0
                    self._hmi_current_id = None
                    self.hmi_persistent = False
                    self._display_changed = True
                    self._dequeue_hmi(now)
            return
        
        # Parse new message (Protocol v2)
        msg_id = str(data.get("id", "")).strip() or None
        msg_type = str(data.get("type", "text")).strip()
        text = str(data.get("text", "")).strip()
        image_path = str(data.get("image_path", "")).strip() or None
        
        if msg_type not in ("text", "pic", "alert"):
            return
        if msg_type in ("text", "alert") and not text:
            return
        if msg_type == "pic" and not image_path:
            return
        
        try:
            duration = float(data.get("duration") or self.hmi_default_duration)
        except (TypeError, ValueError):
            duration = self.hmi_default_duration
        
        priority = str(data.get("priority", "normal")).strip()
        sound = bool(data.get("sound", False))
        persistent = bool(data.get("persistent", False))
        tags = data.get("tags", [])
        animation = str(data.get("animation", "none")).strip().lower()
        try:
            animation_duration = float(data.get("animation_duration", 0.5))
        except (TypeError, ValueError):
            animation_duration = 0.5
        animation_duration = max(0.1, min(5.0, animation_duration))
        try:
            font_size = int(data.get("font_size", 80))
        except (TypeError, ValueError):
            font_size = 80
        
        # Store in active messages with metadata
        message_data = {
            "id": msg_id,
            "type": msg_type,
            "text": text,
            "image_path": image_path,
            "duration": max(1.0, duration),
            "priority": priority,
            "sound": sound,
            "persistent": persistent,
            "tags": tags if isinstance(tags, list) else [],
            "font_size": font_size,
            "animation": animation,
            "animation_duration": animation_duration,
            "queued_at": now,
        }
        
        if msg_id:
            self._hmi_active_messages[msg_id] = message_data
        
        # Queue for display
        self._hmi_queue.append(message_data)
        priority_rank = {"high": 0, "normal": 1, "low": 2}
        self._hmi_queue.sort(
            key=lambda item: (
                priority_rank.get(str(item.get("priority", "normal")), 1),
                item.get("queued_at", now),
            )
        )
        
        # If not currently showing anything, start showing this
        if self.hmi_text is None:
            self._dequeue_hmi(now)

    def _poll_hmi_socket(self, now: float) -> None:
        if self._hmi_socket is None:
            return
        while True:
            try:
                payload = self._hmi_socket.recv(32768)
            except BlockingIOError:
                return
            except OSError:
                return
            if not payload:
                return
            try:
                data = json.loads(payload.decode("utf-8", errors="ignore"))
            except (ValueError, TypeError):
                continue
            if isinstance(data, dict):
                self._enqueue_hmi_data(data, now)

    def _dequeue_hmi(self, now: float) -> None:
        """Pop the next queued HMI item and start displaying it."""
        if not self._hmi_queue:
            self.hmi_text = None
            self._hmi_current_id = None
            return
        
        item = self._hmi_queue.pop(0)
        self.hmi_text = item["text"]
        self.hmi_duration = item["duration"]
        self.hmi_until = now + item["duration"]
        self._hmi_current_id = item.get("id")
        self.hmi_type = item.get("type", "text")
        self.hmi_image_path = item.get("image_path")
        self.hmi_font_size = item.get("font_size", 80)
        self.hmi_animation = item.get("animation", "none")
        self.hmi_animation_duration = item.get("animation_duration", 0.5)
        self.hmi_animation_start = now
        self.hmi_scroll_offset = 0.0
        self.hmi_needs_scroll = False

    def _poll_hmi_request(self, now: float) -> None:
        self._poll_hmi_socket(now)
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
        if isinstance(data, dict):
            self._enqueue_hmi_data(data, now)

    def _get_hmi_font(self) -> pygame.font.Font:
        if self._hmi_font is None or self._hmi_font_size != self.hmi_font_size:
            self._hmi_font_size = self.hmi_font_size
            self._hmi_font = pygame.font.Font(None, max(8, min(128, self.hmi_font_size)))
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

    def _update_scroll_position(self, now: float, text_height: int, max_height: int) -> None:
        """Update vertical scroll position at 30px/second (bottom to top)."""
        if text_height <= max_height:
            self.hmi_needs_scroll = False
            self.hmi_scroll_offset = 0.0
            return
        
        self.hmi_needs_scroll = True
        # Scroll speed: 30 pixels per second (vertical)
        scroll_speed = 30.0
        elapsed = now - self.hmi_animation_start
        loop_height = text_height + max_height + 50
        self.hmi_scroll_offset = (elapsed * scroll_speed) % loop_height
    
    def _render_scrolling_text(self, lines: list[str], font: pygame.font.Font, y: int, color_rgb: tuple[int, int, int], line_height: int, max_height: int) -> None:
        """Render multi-line text with vertical scrolling (bottom to top)."""
        text_h = line_height * len(lines)
        
        # If text fits, render normally without scrolling
        if text_h <= max_height:
            for i, line in enumerate(lines):
                lw, _ = font.size(line)
                line_x = (self.driver.width - lw) // 2
                line_y = y + i * line_height
                self.driver.text(line, color_rgb, (line_x, line_y), font=font)
            return
        
        # Text too tall - render with vertical scroll (bottom to top)
        scroll_y = y - int(self.hmi_scroll_offset)
        
        # Render first copy of text lines
        for i, line in enumerate(lines):
            lw, _ = font.size(line)
            line_x = (self.driver.width - lw) // 2
            line_y = scroll_y + i * line_height
            self.driver.text(line, color_rgb, (line_x, line_y), font=font)
        
        # Render second copy for seamless loop
        if scroll_y + text_h < y + max_height:
            for i, line in enumerate(lines):
                lw, _ = font.size(line)
                line_x = (self.driver.width - lw) // 2
                line_y = scroll_y + text_h + 50 + i * line_height
                self.driver.text(line, color_rgb, (line_x, line_y), font=font)
    
    def _get_animation_scale(self, now: float) -> float:
        """Calculate scale (0.0-1.0+) for scaling animations."""
        if self.hmi_animation == "none" or self.hmi_animation_duration <= 0:
            return 1.0
        
        elapsed = now - self.hmi_animation_start
        if elapsed < 0:
            return 0.5 if self.hmi_animation == "zoom_in" else 1.0
        
        progress = min(1.0, elapsed / self.hmi_animation_duration)
        
        if self.hmi_animation == "zoom_in":
            return 0.5 + (progress * 0.5)
        elif self.hmi_animation == "zoom_out":
            return 1.0 - (progress * 0.3)
        
        return 1.0

    def _get_animation_alpha(self, now: float) -> float:
        """Calculate alpha (0.0-1.0) for fade/pulse/blink animations."""
        if self.hmi_animation == "none" or self.hmi_animation_duration <= 0:
            return 1.0
        
        elapsed = now - self.hmi_animation_start
        if elapsed < 0:
            return 0.0 if self.hmi_animation == "fade_in" else 1.0
        
        progress = min(1.0, elapsed / self.hmi_animation_duration)
        
        if self.hmi_animation == "fade_in":
            return progress
        elif self.hmi_animation == "fade_out":
            return 1.0 - progress
        elif self.hmi_animation == "pulse":
            return 0.5 + 0.5 * math.cos(progress * math.pi * 2)
        elif self.hmi_animation == "blink":
            blink_cycle = int(progress * 6) % 2
            return 1.0 if blink_cycle == 0 else 0.3
        
        return 1.0

    def _load_hmi_image(self, image_path: str) -> pygame.Surface | None:
        """Load and cache HMI image."""
        cached = self._hmi_image_cache.get(image_path)
        if cached is not None:
            return cached
        try:
            image = pygame.image.load(image_path).convert_alpha()
        except (OSError, pygame.error):
            return None
        self._hmi_image_cache[image_path] = image
        return image

    def _render_hmi_image(self, image_path: str, bounds: tuple[int, int, int, int], alpha: float = 1.0, scale: float = 1.0) -> int:
        image = self._load_hmi_image(image_path)
        if image is None:
            return bounds[1]

        x, y, max_w, max_h = bounds
        img_w, img_h = image.get_size()
        if img_w <= 0 or img_h <= 0:
            return y

        # Apply scale from animation
        base_scale = min(max_w / img_w, max_h / img_h, 1.0)
        final_scale = base_scale * scale
        target_size = (max(1, int(img_w * final_scale)), max(1, int(img_h * final_scale)))
        
        if target_size != (img_w, img_h):
            image = pygame.transform.smoothscale(image, target_size)
        
        # Apply alpha blending if not at full opacity
        if alpha < 1.0:
            image = image.copy()
            image.set_alpha(int(255 * alpha))
        
        draw_x = x + (max_w - target_size[0]) // 2
        self.driver.blit(image, (draw_x, y))
        return y + target_size[1]

    def _render_hmi_overlay(self, now: float) -> None:
        W, H = self.driver.width, self.driver.height
        self.driver.fill((10, 12, 22))

        padding = 16
        panel_rect = (padding, padding, W - 2 * padding, H - 2 * padding)
        self.driver.rect((22, 28, 52), panel_rect)
        self.driver.rect((80, 130, 210), panel_rect, 2)

        # Get animation effects
        anim_alpha = self._get_animation_alpha(now)
        anim_scale = self._get_animation_scale(now)
        
        # For typewriter animation
        if self.hmi_animation == "typewriter":
            elapsed = now - self.hmi_animation_start
            progress = min(1.0, elapsed / max(0.1, self.hmi_animation_duration))
            char_count = int(len(self.hmi_text or "") * progress)
            display_text = (self.hmi_text or "")[:char_count]
        else:
            display_text = self.hmi_text or ""
        
        # Skip rendering if alpha is near 0 (fade out)
        if anim_alpha < 0.01 and self.hmi_animation in ("fade_out",):
            return

        font = self._get_hmi_font()
        text_margin = 20
        wrap_width = W - 2 * padding - 2 * text_margin
        image_bottom = padding + text_margin

        if self.hmi_type == "pic" and self.hmi_image_path:
            image_bounds = (
                padding + text_margin,
                padding + text_margin,
                wrap_width,
                max(60, H - 2 * padding - 3 * text_margin - 58),
            )
            image_bottom = self._render_hmi_image(self.hmi_image_path, image_bounds, anim_alpha, anim_scale) + 12

        # Check if text needs scrolling and update scroll position
        test_lines = self._wrap_text(display_text, font, wrap_width)
        test_line_h = font.get_linesize()
        test_total_h = test_line_h * len(test_lines)
        
        # Calculate available height for text
        if self.hmi_type == "pic" and self.hmi_image_path:
            available_height = H - image_bottom - padding - 60
            start_y = image_bottom
        else:
            available_height = H - 2 * padding - 60
            # Center vertically if text fits
            if test_total_h <= available_height:
                start_y = padding + (available_height - test_total_h) // 2
            else:
                start_y = padding + 20
        
        # Check if text needs vertical scrolling
        if test_total_h > available_height and self.hmi_animation != "typewriter":
            # Use vertical scrolling (bottom to top)
            self._update_scroll_position(now, test_total_h, available_height)
            
            color_rgb = (220, 238, 255)
            if anim_alpha < 1.0:
                color_rgb = tuple(int(c * anim_alpha) for c in color_rgb)
            
            self._render_scrolling_text(test_lines, font, start_y, color_rgb, test_line_h, available_height)
        else:
            # Normal multi-line rendering (no scrolling)
            if self.hmi_animation != "typewriter":
                self.hmi_needs_scroll = False
            
            lines = test_lines
            line_h = test_line_h
            
            for i, line in enumerate(lines):
                lw, _ = font.size(line)
                x = (W - lw) // 2
                y = start_y + i * line_h
                color_rgb = (220, 238, 255)
                # Apply alpha for fade/pulse animations
                if anim_alpha < 1.0:
                    color_rgb = tuple(int(c * anim_alpha) for c in color_rgb)
                self.driver.text(line, color_rgb, (x, y), font=font)

        remaining = max(0.0, self.hmi_until - now)
        frac = 1.0 if self.hmi_persistent else (remaining / self.hmi_duration if self.hmi_duration > 0 else 0.0)
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
