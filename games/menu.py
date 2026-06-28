#!/usr/bin/env python3
"""Game selection menu — shown on double-tap from the face screen."""

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


# Each entry: (key, display_name, accent_colour)
GAME_LIST = [
    ("flappy",   "Flappy Dino",  (100, 210,  80)),
    ("snake",    "Snake",        ( 60, 200, 120)),
    ("breakout", "Breakout",     ( 80, 140, 255)),
]

_HEADER_H = 52   # pixels reserved for the title row


class GameMenu:
    """Full-screen game picker.  selected is set when the user picks a game."""

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
        self._touch = touch_driver
        self._driver = driver
        self._rotate_180 = rotate_180
        self._use_sdl = surface is None and driver is None

        if surface is not None:
            self.surface = surface
        else:
            self.surface = pygame.display.set_mode((screen_width, screen_height))

        self.running: bool = True
        self.selected: str | None = None

        self._item_h = (screen_height - _HEADER_H) // len(GAME_LIST)
        self._prev_touched = False
        self._last_touch_time = 0.0
        self._highlight_idx = -1
        self._highlight_until = 0.0

    # ── input ──────────────────────────────────────────────────────────────

    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key in (pygame.K_1, pygame.K_KP1):
                    self._pick(0)
                elif event.key in (pygame.K_2, pygame.K_KP2):
                    self._pick(1)
                elif event.key in (pygame.K_3, pygame.K_KP3):
                    self._pick(2)

        if self._touch is None:
            return

        pressed, rx, ry = self._touch.poll_xy()
        rising = pressed and not self._prev_touched
        self._prev_touched = pressed

        if rising:
            now = time.time()
            if now - self._last_touch_time < 0.25:     # debounce
                self._last_touch_time = now
                return
            self._last_touch_time = now

            _sx, sy = _to_screen(rx, ry, self.screen_width, self.screen_height,
                                  self._rotate_180)
            if sy < _HEADER_H:
                return  # tapped the header area

            idx = (sy - _HEADER_H) // self._item_h
            if 0 <= idx < len(GAME_LIST):
                self._pick(idx)

    def _pick(self, idx: int) -> None:
        self._highlight_idx = idx
        self._highlight_until = time.time() + 0.12
        self.selected = GAME_LIST[idx][0]
        self.running = False

    # ── drawing ────────────────────────────────────────────────────────────

    def draw(self) -> bool:
        """Draw the menu. Returns True if present was handled internally."""
        self.surface.fill((8, 10, 22))

        # ── header ──────────────────────────────────────────────────────
        hfont = pygame.font.Font(None, 40)
        title = hfont.render("SELECT GAME", True, (180, 180, 255))
        self.surface.blit(title, title.get_rect(center=(self.screen_width // 2, _HEADER_H // 2)))
        pygame.draw.line(self.surface, (50, 50, 110),
                         (0, _HEADER_H - 1), (self.screen_width - 1, _HEADER_H - 1), 2)

        # ── game rows ───────────────────────────────────────────────────
        now = time.time()
        nfont = pygame.font.Font(None, 46)
        sfont = pygame.font.Font(None, 24)

        for i, (key, name, color) in enumerate(GAME_LIST):
            y0 = _HEADER_H + i * self._item_h
            yc = y0 + self._item_h // 2
            lit = (i == self._highlight_idx and now < self._highlight_until)

            # row background
            bg = (color[0] // 5, color[1] // 5, color[2] // 5) if not lit else \
                 (color[0] // 2, color[1] // 2, color[2] // 2)
            pygame.draw.rect(self.surface, bg, (0, y0 + 1, self.screen_width, self._item_h - 1))

            # left accent bar
            pygame.draw.rect(self.surface, color, (0, y0 + 1, 8, self._item_h - 1))

            # number badge
            badge = pygame.Rect(16, yc - 16, 32, 32)
            pygame.draw.rect(self.surface, color, badge, border_radius=8)
            num = sfont.render(str(i + 1), True, (0, 0, 0))
            self.surface.blit(num, num.get_rect(center=badge.center))

            # game name
            txt = nfont.render(name, True, (235, 235, 245))
            self.surface.blit(txt, (60, yc - txt.get_height() // 2))

            # separator
            if i < len(GAME_LIST) - 1:
                pygame.draw.line(self.surface, (35, 35, 65),
                                 (0, y0 + self._item_h), (self.screen_width - 1, y0 + self._item_h))

        # tap hint bottom-right
        hint = sfont.render("ESC = back", True, (70, 70, 100))
        self.surface.blit(hint, hint.get_rect(bottomright=(self.screen_width - 6, self.screen_height - 4)))

        if self._driver is not None:
            self._driver.present()
            return True
        if self._use_sdl:
            pygame.display.flip()
            return True
        return False
