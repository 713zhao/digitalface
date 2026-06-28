#!/usr/bin/env python3
"""Snake game — classic grid snake, tap left/right to turn counter/clockwise."""

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
_CELL = 24          # cell size in pixels
_COLS = 20          # 20 × 24 = 480 px  (fills full width)
_ROWS = 11          # 11 × 24 = 264 px  → 10 px top/bottom margin in 284 px game area
_MARGIN_Y = 10      # (284 - 264) // 2

# Directions (dx, dy)
_R = (1, 0)
_D = (0, 1)
_L = (-1, 0)
_U = (0, -1)

# Turning tables
_CCW = {_R: _U, _U: _L, _L: _D, _D: _R}   # counter-clockwise (tap left half)
_CW  = {_R: _D, _D: _L, _L: _U, _U: _R}   # clockwise          (tap right half)


class SnakeGame:
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
            pygame.display.set_caption("Snake")

        self._status_view = self.surface.subsurface((0, 0, screen_width, _STATUS_BAR_H))
        self._game_view   = self.surface.subsurface((0, _STATUS_BAR_H, screen_width, self.game_h))

        self.running = True
        self.back_to_menu = False
        self._prev_touched = False
        self._last_touch_time = 0.0
        self._touch_debounce = 0.18

        self._status_dirty = True
        self._last_status = (-1, -1)

        self._reset()

    # ── game state ──────────────────────────────────────────────────────────

    def _reset(self) -> None:
        cx, cy = _COLS // 2, _ROWS // 2
        self.snake = [(cx - 1, cy), (cx, cy)]   # head is last element
        self.direction = _R
        self._next_dir = _R
        self.food = self._rand_food()
        self.score = 0                           # food eaten
        self._speed = 5.0                        # moves/sec
        self._last_move = time.time()
        self.game_over = False
        self.game_over_at = 0.0
        self.game_over_timeout = 30.0
        self.back_to_menu = False
        self._status_dirty = True
        self._last_status = (-1, -1)

    def _rand_food(self) -> tuple[int, int]:
        while True:
            pos = (random.randint(0, _COLS - 1), random.randint(0, _ROWS - 1))
            if pos not in self.snake:
                return pos

    def _cell_rect(self, col: int, row: int) -> pygame.Rect:
        x = col * _CELL + 1
        y = _MARGIN_Y + row * _CELL + 1
        return pygame.Rect(x, y, _CELL - 2, _CELL - 2)

    # ── input ───────────────────────────────────────────────────────────────

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_SPACE and self.game_over:
                    self._reset()
                elif event.key == pygame.K_LEFT:
                    self._next_dir = _CCW[self.direction]
                elif event.key == pygame.K_RIGHT:
                    self._next_dir = _CW[self.direction]
                elif event.key == pygame.K_UP and self.direction != _D:
                    self._next_dir = _U
                elif event.key == pygame.K_DOWN and self.direction != _U:
                    self._next_dir = _D

        if self._touch is None:
            return

        pressed, rx, ry = self._touch.poll_xy()
        rising = pressed and not self._prev_touched
        self._prev_touched = pressed

        if not rising:
            return

        now = time.time()
        if now - self._last_touch_time < self._touch_debounce:
            self._last_touch_time = now
            return
        self._last_touch_time = now

        if self.game_over:
            self._reset()
            return

        sx, sy = _to_screen(rx, ry, self.screen_width, self.screen_height, self._rotate_180)
        # Status bar back button (top-left 40px)
        if sy < _STATUS_BAR_H and sx < 40:
            self.back_to_menu = True
            self.running = False
            return
        # Left half = turn CCW, right half = turn CW
        if sx < self.screen_width // 2:
            self._next_dir = _CCW[self.direction]
        else:
            self._next_dir = _CW[self.direction]

    # ── update ──────────────────────────────────────────────────────────────

    def update(self) -> None:
        if self.game_over:
            if time.time() - self.game_over_at >= self.game_over_timeout:
                self.running = False
            return

        if time.time() - self._last_move < 1.0 / self._speed:
            return
        self._last_move = time.time()

        # Apply queued turn (cannot reverse 180°)
        nd = self._next_dir
        if (nd[0] + self.direction[0], nd[1] + self.direction[1]) != (0, 0):
            self.direction = nd

        hx, hy = self.snake[-1]
        new_head = (hx + self.direction[0], hy + self.direction[1])

        # Wall collision
        if not (0 <= new_head[0] < _COLS and 0 <= new_head[1] < _ROWS):
            self.game_over = True
            self.game_over_at = time.time()
            return

        # Self collision
        if new_head in self.snake:
            self.game_over = True
            self.game_over_at = time.time()
            return

        self.snake.append(new_head)

        if new_head == self.food:
            self.score += 1
            self.food = self._rand_food()
            self._speed = min(5.0 + self.score * 0.4, 16.0)
        else:
            self.snake.pop(0)

    # ── drawing ─────────────────────────────────────────────────────────────

    def draw(self) -> bool:
        # Status bar — only when changed
        status = (len(self.snake), self.score)
        if status != self._last_status:
            self._draw_status()
            self._last_status = status
            self._status_dirty = True

        # Background grid
        self._game_view.fill((10, 20, 10))
        gc = (15, 28, 15)
        for c in range(_COLS + 1):
            x = c * _CELL
            pygame.draw.line(self._game_view, gc, (x, _MARGIN_Y), (x, _MARGIN_Y + _ROWS * _CELL))
        for r in range(_ROWS + 1):
            y = _MARGIN_Y + r * _CELL
            pygame.draw.line(self._game_view, gc, (0, y), (_COLS * _CELL, y))

        # Food
        fr = self._cell_rect(*self.food)
        pygame.draw.ellipse(self._game_view, (255, 70, 70), fr)
        pygame.draw.ellipse(self._game_view, (255, 150, 100), fr.inflate(-4, -4))

        # Snake body
        for i, seg in enumerate(self.snake):
            sr = self._cell_rect(*seg)
            is_head = (i == len(self.snake) - 1)
            color = (120, 255, 120) if is_head else (60, 180, 60)
            r = 6 if is_head else 3
            pygame.draw.rect(self._game_view, color, sr, border_radius=r)
            if is_head:
                # eye dots
                ex = sr.x + sr.width - 5
                ey = sr.y + 5
                pygame.draw.circle(self._game_view, (0, 0, 0), (ex, ey), 2)

        # Direction hint (small arrows at bottom of grid)
        af = pygame.font.Font(None, 20)
        hint = af.render("◄ turn   turn ►", True, (40, 80, 40))
        self._game_view.blit(hint, hint.get_rect(center=(self.screen_width // 2,
                                                          _MARGIN_Y + _ROWS * _CELL + 8)))

        # Game over overlay
        if self.game_over:
            ov = pygame.Surface((self.screen_width, self.game_h))
            ov.set_alpha(170)
            ov.fill((0, 0, 0))
            self._game_view.blit(ov, (0, 0))
            f1 = pygame.font.Font(None, 48)
            f2 = pygame.font.Font(None, 30)
            f3 = pygame.font.Font(None, 24)
            cx, cy = self.screen_width // 2, self.game_h // 2
            self._game_view.blit(f1.render("GAME OVER", True, (255, 80, 80)),
                                  f1.render("GAME OVER", True, (255, 80, 80)).get_rect(center=(cx, cy - 35)))
            self._game_view.blit(f2.render(f"Length: {len(self.snake)}  Food: {self.score}",
                                           True, (255, 255, 255)),
                                  f2.render(f"Length: {len(self.snake)}  Food: {self.score}",
                                            True, (255, 255, 255)).get_rect(center=(cx, cy + 5)))
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
        s = font.render(f"Length: {len(self.snake)}", True, (230, 230, 230))
        self._status_view.blit(s, (44, 6))
        r = font.render(f"Food: {self.score}", True, (255, 120, 120))
        self._status_view.blit(r, r.get_rect(topright=(self.screen_width - 8, 6)))
        spd = pygame.font.Font(None, 20)
        sp = spd.render(f"{self._speed:.1f} mv/s", True, (80, 120, 80))
        self._status_view.blit(sp, sp.get_rect(center=(self.screen_width // 2, _STATUS_BAR_H // 2)))
        pygame.draw.line(self._status_view, (50, 50, 80),
                         (0, _STATUS_BAR_H - 1), (self.screen_width - 1, _STATUS_BAR_H - 1))
