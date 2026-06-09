#!/usr/bin/env python3
"""Basic digital face for Raspberry Pi LCD using pygame."""

import argparse
import math
import os
import signal
import time

import pygame


WIDTH = 480
HEIGHT = 320
FPS = 30


BG_COLOR = (14, 18, 26)
HEAD_COLOR = (40, 53, 78)
EYE_COLOR = (220, 240, 255)
PUPIL_COLOR = (15, 18, 28)
MOUTH_COLOR = (130, 210, 255)
ACCENT_COLOR = (255, 196, 92)


class DigitalFace:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.expression = "neutral"
        self.blink_closed_until = 0.0
        self.next_blink_at = time.time() + 2.0
        self.fullscreen = True

    def set_expression(self, name: str) -> None:
        if name in {"neutral", "happy", "listening", "surprised"}:
            self.expression = name

    def update(self, now: float) -> None:
        if now >= self.next_blink_at:
            self.blink_closed_until = now + 0.12
            self.next_blink_at = now + 2.5

    def draw(self, t: float) -> None:
        self.screen.fill(BG_COLOR)

        cx = WIDTH // 2
        cy = HEIGHT // 2

        head_rect = pygame.Rect(70, 30, WIDTH - 140, HEIGHT - 60)
        pygame.draw.ellipse(self.screen, HEAD_COLOR, head_rect)

        if self.expression == "listening":
            pulse = (math.sin(t * 8.0) + 1.0) / 2.0
            ring_radius = int(120 + pulse * 10)
            pygame.draw.circle(self.screen, ACCENT_COLOR, (cx, cy), ring_radius, 3)

        self._draw_eyes(cx, cy, t)
        self._draw_mouth(cx, cy)

    def _draw_eyes(self, cx: int, cy: int, t: float) -> None:
        eye_y = cy - 48
        eye_dx = 75
        eye_w = 68
        eye_h = 48

        blink = time.time() <= self.blink_closed_until
        if blink:
            pygame.draw.line(self.screen, EYE_COLOR, (cx - eye_dx - 28, eye_y), (cx - eye_dx + 28, eye_y), 5)
            pygame.draw.line(self.screen, EYE_COLOR, (cx + eye_dx - 28, eye_y), (cx + eye_dx + 28, eye_y), 5)
            return

        left_eye = pygame.Rect(cx - eye_dx - eye_w // 2, eye_y - eye_h // 2, eye_w, eye_h)
        right_eye = pygame.Rect(cx + eye_dx - eye_w // 2, eye_y - eye_h // 2, eye_w, eye_h)
        pygame.draw.ellipse(self.screen, EYE_COLOR, left_eye)
        pygame.draw.ellipse(self.screen, EYE_COLOR, right_eye)

        if self.expression == "listening":
            offset_x = int(math.sin(t * 3.0) * 8)
            offset_y = int(math.cos(t * 2.4) * 4)
        else:
            offset_x = int(math.sin(t * 1.2) * 4)
            offset_y = int(math.cos(t * 1.0) * 3)

        pupil_r = 10 if self.expression != "surprised" else 7
        pygame.draw.circle(self.screen, PUPIL_COLOR, (cx - eye_dx + offset_x, eye_y + offset_y), pupil_r)
        pygame.draw.circle(self.screen, PUPIL_COLOR, (cx + eye_dx + offset_x, eye_y + offset_y), pupil_r)

    def _draw_mouth(self, cx: int, cy: int) -> None:
        if self.expression == "happy":
            pygame.draw.arc(self.screen, MOUTH_COLOR, (cx - 70, cy - 10, 140, 80), 0.15, 2.95, 6)
        elif self.expression == "surprised":
            pygame.draw.circle(self.screen, MOUTH_COLOR, (cx, cy + 62), 20, 5)
        elif self.expression == "listening":
            pygame.draw.arc(self.screen, MOUTH_COLOR, (cx - 60, cy + 15, 120, 30), 3.14, 6.28, 5)
        else:
            pygame.draw.line(self.screen, MOUTH_COLOR, (cx - 48, cy + 58), (cx + 48, cy + 58), 5)


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
    pygame.init()
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
    pygame.init()
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
            clock.tick(8)
    finally:
        fb.close()
        pygame.quit()


def main() -> None:
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
