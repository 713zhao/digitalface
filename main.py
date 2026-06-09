#!/usr/bin/env python3
"""Fancy digital face for Raspberry Pi LCD using pygame."""

import argparse
import fcntl
import math
import os
import signal
import time

import pygame


WIDTH = 480
HEIGHT = 320
FPS = 30
FB_FPS = 8
LOCK_FILE = "/tmp/digitalface.lock"
FACE_CONTROL_FILE = "/tmp/digitalface_expression"
_lock_handle = None

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


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def acquire_single_instance_lock() -> bool:
    global _lock_handle
    _lock_handle = open(LOCK_FILE, "w")
    try:
        fcntl.flock(_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_handle.write(str(os.getpid()))
        _lock_handle.flush()
        return True
    except BlockingIOError:
        return False


class DigitalFace:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.expression = "happy"
        self.blink_closed_until = 0.0
        self.next_blink_at = time.time() + 2.2
        self.fullscreen = True
        self.ui_font = pygame.font.Font(None, 24)
        self.bg_cache: dict[str, pygame.Surface] = {}
        self.next_control_poll_at = 0.0

    def set_expression(self, name: str) -> None:
        if name in THEMES:
            self.expression = name

    def update(self, now: float) -> None:
        if now >= self.next_control_poll_at:
            self._poll_external_expression()
            self.next_control_poll_at = now + 0.35

        if now >= self.next_blink_at:
            self.blink_closed_until = now + 0.10
            self.next_blink_at = now + 2.0 + (math.sin(now) + 1.0) * 0.4

    def _theme(self) -> dict:
        return THEMES.get(self.expression, THEMES["happy"])

    def _poll_external_expression(self) -> None:
        try:
            with open(FACE_CONTROL_FILE, "r", encoding="utf-8") as f:
                requested = f.read().strip().lower()
        except FileNotFoundError:
            return
        except OSError:
            return

        if requested in THEMES and requested != self.expression:
            self.set_expression(requested)

    def _draw_vertical_gradient(self, surface: pygame.Surface, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> None:
        for y in range(HEIGHT):
            t = y / (HEIGHT - 1)
            color = (_lerp(top[0], bottom[0], t), _lerp(top[1], bottom[1], t), _lerp(top[2], bottom[2], t))
            pygame.draw.line(surface, color, (0, y), (WIDTH, y))

    def _draw_soft_circle(self, surface: pygame.Surface, center: tuple[int, int], radius: int, color: tuple[int, int, int], alpha: int) -> None:
        diameter = radius * 2
        glow = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
        for ring in range(radius, 0, -8):
            ring_alpha = max(0, int(alpha * (ring / radius) ** 2))
            pygame.draw.circle(glow, (*color, ring_alpha), (radius, radius), ring)
        surface.blit(glow, (center[0] - radius, center[1] - radius))

    def _build_background(self, expr: str) -> pygame.Surface:
        theme = THEMES[expr]
        bg = pygame.Surface((WIDTH, HEIGHT))
        self._draw_vertical_gradient(bg, theme["bg_top"], theme["bg_bottom"])

        cx = WIDTH // 2
        self._draw_soft_circle(bg, (cx - 130, 68), 88, theme["accent"], 72)
        self._draw_soft_circle(bg, (cx + 148, 84), 76, theme["accent_2"], 70)

        strip = pygame.Rect(0, HEIGHT - 34, WIDTH, 34)
        pygame.draw.rect(bg, (10, 12, 20), strip)
        pygame.draw.line(bg, theme["accent"], (0, HEIGHT - 34), (WIDTH, HEIGHT - 34), 2)
        pygame.draw.circle(bg, theme["accent"], (16, HEIGHT - 17), 4)

        label = self.ui_font.render(theme["label"], True, (232, 240, 255))
        bg.blit(label, (30, HEIGHT - 25))
        return bg

    def _get_background(self, expr: str) -> pygame.Surface:
        if expr not in self.bg_cache:
            self.bg_cache[expr] = self._build_background(expr)
        return self.bg_cache[expr]

    def draw(self, t: float) -> None:
        theme = self._theme()
        self.screen.blit(self._get_background(self.expression), (0, 0))

        cx = WIDTH // 2
        cy = HEIGHT // 2 - 2

        # Lightweight animated aura.
        pulse = (math.sin(t * 2.2) + 1.0) * 0.5
        aura_radius = int(112 + pulse * 10)
        pygame.draw.circle(self.screen, theme["accent"], (cx, cy), aura_radius, 2)

        # Head and "ears" for a more character-like silhouette.
        head_rect = pygame.Rect(86, 36, WIDTH - 172, HEIGHT - 100)
        pygame.draw.ellipse(self.screen, theme["face"], head_rect)
        pygame.draw.ellipse(self.screen, theme["accent"], head_rect, 3)

        ear_y = cy - 36
        pygame.draw.circle(self.screen, theme["face"], (cx - 126, ear_y), 22)
        pygame.draw.circle(self.screen, theme["face"], (cx + 126, ear_y), 22)
        pygame.draw.circle(self.screen, theme["accent_2"], (cx - 126, ear_y), 10)
        pygame.draw.circle(self.screen, theme["accent_2"], (cx + 126, ear_y), 10)

        self._draw_eyes(cx, cy, t, theme)
        self._draw_mouth(cx, cy, theme)

    def _draw_eyes(self, cx: int, cy: int, t: float, theme: dict) -> None:
        eye_y = cy - 44
        eye_dx = 76
        eye_w = 74
        eye_h = 52

        blink = time.time() <= self.blink_closed_until
        if blink:
            pygame.draw.line(self.screen, theme["eye"], (cx - eye_dx - 30, eye_y), (cx - eye_dx + 30, eye_y), 6)
            pygame.draw.line(self.screen, theme["eye"], (cx + eye_dx - 30, eye_y), (cx + eye_dx + 30, eye_y), 6)
            return

        left_eye = pygame.Rect(cx - eye_dx - eye_w // 2, eye_y - eye_h // 2, eye_w, eye_h)
        right_eye = pygame.Rect(cx + eye_dx - eye_w // 2, eye_y - eye_h // 2, eye_w, eye_h)
        pygame.draw.ellipse(self.screen, theme["eye"], left_eye)
        pygame.draw.ellipse(self.screen, theme["eye"], right_eye)

        if self.expression == "listening":
            offset_x = int(math.sin(t * 2.8) * 7)
            offset_y = int(math.cos(t * 2.2) * 3)
        elif self.expression == "surprised":
            offset_x = 0
            offset_y = -1
        else:
            offset_x = int(math.sin(t * 1.0) * 2)
            offset_y = int(math.cos(t * 0.8) * 2)

        pupil_r = 8 if self.expression == "surprised" else 11
        pygame.draw.circle(self.screen, theme["pupil"], (cx - eye_dx + offset_x, eye_y + offset_y), pupil_r)
        pygame.draw.circle(self.screen, theme["pupil"], (cx + eye_dx + offset_x, eye_y + offset_y), pupil_r)
        pygame.draw.circle(self.screen, (255, 255, 255), (cx - eye_dx + offset_x - 3, eye_y + offset_y - 4), 2)
        pygame.draw.circle(self.screen, (255, 255, 255), (cx + eye_dx + offset_x - 3, eye_y + offset_y - 4), 2)

    def _draw_mouth(self, cx: int, cy: int, theme: dict) -> None:
        if self.expression == "happy":
            pygame.draw.arc(self.screen, theme["mouth"], (cx - 74, cy + 0, 148, 88), 3.25, 6.17, 7)
        elif self.expression == "surprised":
            pygame.draw.circle(self.screen, theme["mouth"], (cx, cy + 64), 22, 6)
        elif self.expression == "listening":
            pygame.draw.arc(self.screen, theme["mouth"], (cx - 64, cy + 17, 128, 34), 3.14, 6.28, 6)
        else:
            pygame.draw.line(self.screen, theme["mouth"], (cx - 52, cy + 60), (cx + 52, cy + 60), 6)


class FramebufferDisplay:
    def __init__(self, fbdev: str, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.fd = os.open(fbdev, os.O_RDWR)
        self.surface = pygame.Surface((width, height))
        self.frame = bytearray(width * height * 2)

    def _rgb888_to_rgb565(self, rgb_bytes: bytes) -> bytes:
        src = memoryview(rgb_bytes)
        dst = self.frame
        j = 0
        for i in range(0, len(src), 3):
            r = src[i]
            g = src[i + 1]
            b = src[i + 2]
            val = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            dst[j] = val & 0xFF
            dst[j + 1] = (val >> 8) & 0xFF
            j += 2
        return dst

    def present(self) -> None:
        rgb = pygame.image.tostring(self.surface, "RGB")
        fb_bytes = self._rgb888_to_rgb565(rgb)
        os.lseek(self.fd, 0, os.SEEK_SET)
        os.write(self.fd, fb_bytes)

    def close(self) -> None:
        os.close(self.fd)


def run_sdl_mode() -> None:
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_caption("Digital Face")

    flags = pygame.FULLSCREEN
    screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)

    clock = pygame.time.Clock()
    face = DigitalFace(screen)

    running = True
    while running:
        now = time.time()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_1:
                    face.set_expression("neutral")
                elif event.key == pygame.K_2:
                    face.set_expression("happy")
                elif event.key == pygame.K_3:
                    face.set_expression("listening")
                elif event.key == pygame.K_4:
                    face.set_expression("surprised")
                elif event.key == pygame.K_f:
                    face.fullscreen = not face.fullscreen
                    mode = pygame.FULLSCREEN if face.fullscreen else 0
                    screen = pygame.display.set_mode((WIDTH, HEIGHT), mode)
                    face.screen = screen

        face.update(now)
        face.draw(now)
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


def run_framebuffer_mode(fbdev: str) -> None:
    pygame.font.init()
    fb = FramebufferDisplay(fbdev, WIDTH, HEIGHT)
    clock = pygame.time.Clock()
    face = DigitalFace(fb.surface)

    running = True

    def stop_handler(_sig: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    try:
        while running:
            now = time.time()
            face.update(now)
            face.draw(now)
            fb.present()
            clock.tick(FB_FPS)
    finally:
        fb.close()
        pygame.quit()


def main() -> None:
    if not acquire_single_instance_lock():
        print("digitalface is already running; exiting second instance")
        return

    parser = argparse.ArgumentParser(description="Digital face for Raspberry Pi LCD")
    parser.add_argument("--fbdev", default="/dev/fb1", help="Framebuffer device for fallback mode")
    parser.add_argument("--force-fb", action="store_true", help="Force direct framebuffer mode")
    args = parser.parse_args()

    if args.force_fb:
        run_framebuffer_mode(args.fbdev)
        return

    try:
        run_sdl_mode()
    except pygame.error as exc:
        if "not available" in str(exc) and os.path.exists(args.fbdev):
            run_framebuffer_mode(args.fbdev)
            return
        raise


if __name__ == "__main__":
    main()
