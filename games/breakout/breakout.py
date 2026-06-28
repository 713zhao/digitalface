#!/usr/bin/env python3
"""Breakout / Brick Breaker — tap to position paddle, clear all bricks to win."""

import math
import random
import time
import pygame

try:
    from driver.display_driver import touch_to_screen as _to_screen
except ImportError:
    import os as _os

    def _to_screen(rx, ry, w, h, rotate_180=True):  # type: ignore[misc]
        if rx < 0:
            return w // 2, h // 2
        xmin = int(_os.environ.get("DIGITALFACE_TOUCH_X_MIN", "200"))
        xmax = int(_os.environ.get("DIGITALFACE_TOUCH_X_MAX", "3900"))
        ymin = int(_os.environ.get("DIGITALFACE_TOUCH_Y_MIN", "200"))
        ymax = int(_os.environ.get("DIGITALFACE_TOUCH_Y_MAX", "3900"))
        sx = (rx - xmin) / max(xmax - xmin, 1) * w
        sy = (ry - ymin) / max(ymax - ymin, 1) * h
        if rotate_180:
            sx, sy = w - 1 - sx, h - 1 - sy
        return int(max(0, min(w - 1, sx))), int(max(0, min(h - 1, sy)))


_STATUS_BAR_H = 36

# Brick layout
_BRICK_ROWS = 5
_BRICK_COLS = 10
_BRICK_W    = 44
_BRICK_H    = 14
_BRICK_GAP_X = 4
_BRICK_GAP_Y = 4
_BRICKS_MARGIN_X = (480 - (_BRICK_COLS * _BRICK_W + (_BRICK_COLS - 1) * _BRICK_GAP_X)) // 2  # = 2
_BRICKS_START_Y  = 12   # top of first brick row (game-area coords)

# Paddle
_PAD_W = 80
_PAD_H = 10
_PAD_Y_OFFSET = 18   # distance from bottom of game area

# Ball
_BALL_R = 7
_BALL_SPEED = 230.0  # px/sec

_ROW_COLORS = [
    (255,  70,  70),   # row 0 — red    (top, hardest to reach)
    (255, 155,  40),   # row 1 — orange
    (240, 220,  40),   # row 2 — yellow
    ( 80, 210,  80),   # row 3 — green
    ( 80, 160, 255),   # row 4 — blue   (bottom, easiest)
]


class BreakoutGame:
    def __init__(
        self,
        screen_width: int = 480,
        screen_height: int = 320,
        surface: pygame.Surface | None = None,
        touch_driver=None,
        driver=None,
        rotate_180: bool = True,
    ) -> None:
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.game_h = screen_height - _STATUS_BAR_H
        self._touch = touch_driver
        self._driver = driver
        self._rotate_180 = rotate_180
        self._use_sdl = surface is None and driver is None

        if surface is not None:
            self.surface = surface
        else:
            self.surface = pygame.display.set_mode((screen_width, screen_height))
            pygame.display.set_caption("Breakout")

        self._status_view = self.surface.subsurface((0, 0, screen_width, _STATUS_BAR_H))
        self._game_view   = self.surface.subsurface((0, _STATUS_BAR_H, screen_width, self.game_h))

        self.running = True
        self.back_to_menu = False
        self._prev_touched = False
        self._last_touch_time = 0.0
        self._touch_debounce = 0.2
        self._status_dirty = True
        self._last_status = (-1, -1)
        self._last_update = time.time()

        self._reset()

    # ── state ───────────────────────────────────────────────────────────────

    def _reset(self) -> None:
        # Bricks
        self.bricks: list[tuple[pygame.Rect, int]] = []   # (rect, row_idx)
        for row in range(_BRICK_ROWS):
            for col in range(_BRICK_COLS):
                x = _BRICKS_MARGIN_X + col * (_BRICK_W + _BRICK_GAP_X)
                y = _BRICKS_START_Y  + row * (_BRICK_H + _BRICK_GAP_Y)
                self.bricks.append((pygame.Rect(x, y, _BRICK_W, _BRICK_H), row))

        # Paddle
        self.pad_x = float((self.screen_width - _PAD_W) // 2)
        self.pad_y = self.game_h - _PAD_Y_OFFSET - _PAD_H

        # Ball
        self.ball_x = float(self.screen_width // 2)
        self.ball_y = float(self.pad_y - _BALL_R - 1)
        self._ball_speed = _BALL_SPEED
        ang = math.radians(random.uniform(230, 310))
        self.ball_vx = self._ball_speed * math.cos(ang)
        self.ball_vy = -abs(self._ball_speed * math.sin(ang))
        self._launched = False

        self.score = 0
        self.lives = 3
        self.game_over = False
        self.won = False
        self.game_over_at = 0.0
        self.game_over_timeout = 60.0
        self.back_to_menu = False
        self._last_update = time.time()
        self._last_input_time = time.time()
        self._status_dirty = True
        self._last_status = (-1, -1)

    # ── input ───────────────────────────────────────────────────────────────

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_SPACE:
                    if self.game_over:
                        self._reset()
                    else:
                        self._launched = True
                elif event.key == pygame.K_LEFT:
                    self.pad_x = max(0, self.pad_x - 24)
                elif event.key == pygame.K_RIGHT:
                    self.pad_x = min(self.screen_width - _PAD_W, self.pad_x + 24)

        if self._touch is None:
            return

        pressed, rx, ry = self._touch.poll_xy()
        if pressed:
            self._last_input_time = time.time()  # any touch resets idle timer
        rising = pressed and not self._prev_touched
        self._prev_touched = pressed

        if rising:
            now = time.time()
            if now - self._last_touch_time < self._touch_debounce:
                self._last_touch_time = now
                return
            self._last_touch_time = now

            sx, sy = _to_screen(rx, ry, self.screen_width, self.screen_height, self._rotate_180)
            # Status bar back button (top-left 40px)
            if sy < _STATUS_BAR_H and sx < 40:
                self.back_to_menu = True
                self.running = False
                return
            if self.game_over:
                self._reset()
                return
            if not self._launched:
                self._launched = True
                return

        # While finger held — move paddle to track touch X
        if pressed and not self.game_over and self._launched:
            sx, _sy = _to_screen(rx, ry, self.screen_width, self.screen_height, self._rotate_180)
            if sx >= 0:
                target_x = sx - _PAD_W // 2
                self.pad_x = float(max(0, min(self.screen_width - _PAD_W, target_x)))

    # ── update ──────────────────────────────────────────────────────────────

    def update(self) -> None:
        if self.game_over:
            if time.time() - self.game_over_at >= self.game_over_timeout:
                self.running = False
            return

        now = time.time()
        dt = min(now - self._last_update, 0.05)
        self._last_update = now

        if not self._launched:
            self.ball_x = self.pad_x + _PAD_W // 2
            self.ball_y = float(self.pad_y - _BALL_R - 1)
            return

        # Idle timeout — no touch for 60 s exits the game
        if time.time() - self._last_input_time >= 60.0:
            self.running = False
            return

        self.ball_x += self.ball_vx * dt
        self.ball_y += self.ball_vy * dt

        # Side walls
        if self.ball_x - _BALL_R <= 0:
            self.ball_x = float(_BALL_R)
            self.ball_vx = abs(self.ball_vx)
        if self.ball_x + _BALL_R >= self.screen_width:
            self.ball_x = float(self.screen_width - _BALL_R)
            self.ball_vx = -abs(self.ball_vx)

        # Ceiling
        if self.ball_y - _BALL_R <= 0:
            self.ball_y = float(_BALL_R)
            self.ball_vy = abs(self.ball_vy)

        # Lost ball — bottom
        if self.ball_y - _BALL_R >= self.game_h:
            self.lives -= 1
            if self.lives <= 0:
                self.game_over = True
                self.won = False
                self.game_over_at = time.time()
            else:
                self.ball_x = self.pad_x + _PAD_W // 2
                self.ball_y = float(self.pad_y - _BALL_R - 1)
                ang = math.radians(random.uniform(230, 310))
                self.ball_vx = self._ball_speed * math.cos(ang)
                self.ball_vy = -abs(self._ball_speed * math.sin(ang))
                self._launched = False
            return

        # Paddle collision
        pad_rect = pygame.Rect(int(self.pad_x), self.pad_y, _PAD_W, _PAD_H)
        ball_rect = pygame.Rect(int(self.ball_x) - _BALL_R, int(self.ball_y) - _BALL_R,
                                _BALL_R * 2, _BALL_R * 2)
        if ball_rect.colliderect(pad_rect) and self.ball_vy > 0:
            rel = (self.ball_x - (self.pad_x + _PAD_W / 2)) / (_PAD_W / 2)
            ang = math.radians(rel * 55 + 270)
            spd = math.hypot(self.ball_vx, self.ball_vy)
            self.ball_vx = spd * math.sin(ang)
            self.ball_vy = -abs(spd * math.cos(ang))
            # ensure minimum upward velocity
            min_vy = spd * 0.25
            if abs(self.ball_vy) < min_vy:
                self.ball_vy = -min_vy
            self.ball_y = float(self.pad_y - _BALL_R - 1)

        # Brick collisions
        ball_rect = pygame.Rect(int(self.ball_x) - _BALL_R, int(self.ball_y) - _BALL_R,
                                _BALL_R * 2, _BALL_R * 2)
        for brick, row in self.bricks[:]:
            if ball_rect.colliderect(brick):
                self.bricks.remove((brick, row))
                self.score += (5 - row) * 10   # top rows worth more
                # bounce direction based on overlap axis
                dx = abs(self.ball_x - brick.centerx) / brick.width
                dy = abs(self.ball_y - brick.centery) / brick.height
                if dx > dy:
                    self.ball_vx = -self.ball_vx
                else:
                    self.ball_vy = -self.ball_vy
                # gradually speed up
                self._ball_speed = min(_BALL_SPEED + self.score * 0.15, _BALL_SPEED * 1.8)
                break  # one brick per step

        if not self.bricks:
            self.game_over = True
            self.won = True
            self.game_over_at = time.time()

    # ── drawing ─────────────────────────────────────────────────────────────

    def draw(self) -> bool:
        status = (self.score, self.lives)
        if status != self._last_status:
            self._draw_status()
            self._last_status = status
            self._status_dirty = True

        self._game_view.fill((5, 5, 20))

        # Bricks
        for brick, row in self.bricks:
            color = _ROW_COLORS[min(row, len(_ROW_COLORS) - 1)]
            pygame.draw.rect(self._game_view, color, brick, border_radius=3)
            pygame.draw.rect(self._game_view, (255, 255, 255), brick, 1, border_radius=3)

        # Paddle
        pad_rect = pygame.Rect(int(self.pad_x), self.pad_y, _PAD_W, _PAD_H)
        pygame.draw.rect(self._game_view, (100, 180, 255), pad_rect, border_radius=5)
        pygame.draw.rect(self._game_view, (180, 220, 255), pad_rect, 2, border_radius=5)

        # Ball
        pygame.draw.circle(self._game_view, (255, 220, 80),
                            (int(self.ball_x), int(self.ball_y)), _BALL_R)
        pygame.draw.circle(self._game_view, (255, 255, 180),
                            (int(self.ball_x) - 2, int(self.ball_y) - 2), 2)

        # Launch hint
        if not self._launched and not self.game_over:
            f = pygame.font.Font(None, 28)
            h = f.render("TAP TO LAUNCH", True, (200, 200, 100))
            self._game_view.blit(h, h.get_rect(center=(self.screen_width // 2, self.game_h // 2 + 50)))

        # Game over
        if self.game_over:
            ov = pygame.Surface((self.screen_width, self.game_h))
            ov.set_alpha(165)
            ov.fill((0, 0, 0))
            self._game_view.blit(ov, (0, 0))
            f1 = pygame.font.Font(None, 52)
            f2 = pygame.font.Font(None, 32)
            f3 = pygame.font.Font(None, 24)
            cx, cy = self.screen_width // 2, self.game_h // 2
            msg = "YOU WIN!" if self.won else "GAME OVER"
            col = (100, 255, 100) if self.won else (255, 80, 80)
            self._game_view.blit(f1.render(msg, True, col),
                                  f1.render(msg, True, col).get_rect(center=(cx, cy - 35)))
            self._game_view.blit(f2.render(f"Score: {self.score}", True, (255, 255, 255)),
                                  f2.render(f"Score: {self.score}", True, (255, 255, 255)).get_rect(center=(cx, cy + 5)))
            self._game_view.blit(f3.render("TAP TO RESTART", True, (200, 200, 200)),
                                  f3.render("TAP TO RESTART", True, (200, 200, 200)).get_rect(center=(cx, cy + 40)))

        # Present
        if self._driver is not None:
            if self._status_dirty:
                self._driver.present_rows(0, _STATUS_BAR_H)
                self._status_dirty = False
            self._driver.present_rows(_STATUS_BAR_H, self.screen_height)
            return True
        if self._use_sdl:
            pygame.display.flip()
            return True
        return False

    def _draw_status(self) -> None:
        self._status_view.fill((15, 15, 35))
        # Back-to-menu hamburger button (tap anywhere in left 40px of status bar)
        for i in range(3):
            pygame.draw.rect(self._status_view, (140, 140, 190), (7, 8 + i * 7, 18, 3))
        font = pygame.font.Font(None, 30)
        s = font.render(f"Score: {self.score}", True, (230, 230, 230))
        self._status_view.blit(s, (44, 6))
        hearts = "\u2665 " * self.lives
        lf = font.render(hearts, True, (255, 80, 80))
        self._status_view.blit(lf, lf.get_rect(topright=(self.screen_width - 8, 6)))
        pygame.draw.line(self._status_view, (50, 50, 80),
                         (0, _STATUS_BAR_H - 1), (self.screen_width - 1, _STATUS_BAR_H - 1))
