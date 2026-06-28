#!/usr/bin/env python3
"""Flappy Bird Game - Touch screen controlled."""

import math
import random
import time
import pygame

try:
    from driver.display_driver import touch_to_screen as _fb_to_screen
except ImportError:
    import os as _os

    def _fb_to_screen(rx, ry, w, h, rotate_180=True):  # type: ignore[misc]
        if rx < 0 or ry < 0:
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


_STATUS_BAR_H = 36  # pixels reserved at top for status HUD


def _draw_dino(surface: pygame.Surface, cx: int, cy: int, color=(100, 200, 80)) -> None:
    """Draw a pixel-art T-Rex dinosaur centered at (cx, cy) in game coordinates."""
    e = (20, 20, 20)     # eye dark
    w = (255, 255, 255)  # eye shine
    # Tail tip + tail
    pygame.draw.rect(surface, color, (cx - 21, cy,      5,  3))
    pygame.draw.rect(surface, color, (cx - 18, cy - 2,  8,  5))
    # Body
    pygame.draw.rect(surface, color, (cx - 11, cy - 8,  21, 14))
    # Back spine bump
    pygame.draw.rect(surface, color, (cx - 8,  cy - 12, 6,  5))
    # Neck
    pygame.draw.rect(surface, color, (cx + 6,  cy - 12, 6,  8))
    # Head
    pygame.draw.rect(surface, color, (cx + 3,  cy - 18, 12, 11))
    # Snout / lower jaw
    pygame.draw.rect(surface, color, (cx + 9,  cy - 11, 8,  6))
    # Eye
    pygame.draw.rect(surface, e,     (cx + 11, cy - 17, 3,  3))
    pygame.draw.rect(surface, w,     (cx + 12, cy - 17, 2,  2))
    # Arm stub
    pygame.draw.rect(surface, color, (cx + 12, cy - 3,  5,  3))
    # Front leg + foot
    pygame.draw.rect(surface, color, (cx - 3,  cy + 6,  6,  9))
    pygame.draw.rect(surface, color, (cx - 5,  cy + 14, 8,  3))
    # Back leg + foot
    pygame.draw.rect(surface, color, (cx + 5,  cy + 6,  6,  9))
    pygame.draw.rect(surface, color, (cx + 3,  cy + 14, 9,  3))


class Bird:
    """Player bird sprite."""
    
    def __init__(self, x, y, width=20, height=20):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.velocity = 0
        self.gravity = 0.4
        self.jump_power = -6
        self.max_fall_speed = 12
    
    def update(self):
        """Apply gravity and update position."""
        self.velocity += self.gravity
        self.velocity = min(self.velocity, self.max_fall_speed)
        self.y += self.velocity
    
    def jump(self):
        """Make bird jump."""
        self.velocity = self.jump_power
    
    def draw(self, surface, color=(255, 255, 100)):
        """Draw bird as a circle."""
        pygame.draw.circle(surface, color, (int(self.x), int(self.y)), self.width // 2)
    
    def get_rect(self):
        """Return bird bounding rect for collision."""
        return pygame.Rect(self.x - self.width // 2, self.y - self.height // 2, self.width, self.height)


class Pipe:
    """Obstacle pipe."""
    
    def __init__(self, x, gap_y, gap_height, screen_width, screen_height):
        self.x = x
        self.gap_y = gap_y
        self.gap_height = gap_height
        self.width = 60
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.speed = 180  # px/sec default
        self.passed = False
    
    def update(self, dt: float = 1/60):
        """Move pipe left."""
        self.x -= self.speed * dt
    
    def draw(self, surface, color=(0, 200, 0)):
        """Draw pipe (top and bottom sections)."""
        # Top pipe
        if self.gap_y > 0:
            pygame.draw.rect(surface, color, (self.x, 0, self.width, self.gap_y))
        
        # Bottom pipe
        bottom_y = self.gap_y + self.gap_height
        if bottom_y < self.screen_height:
            pygame.draw.rect(surface, color, (self.x, bottom_y, self.width, self.screen_height - bottom_y))
    
    def get_rects(self):
        """Return collision rects for top and bottom pipes."""
        rects = []
        if self.gap_y > 0:
            rects.append(pygame.Rect(self.x, 0, self.width, self.gap_y))
        bottom_y = self.gap_y + self.gap_height
        if bottom_y < self.screen_height:
            rects.append(pygame.Rect(self.x, bottom_y, self.width, self.screen_height - bottom_y))
        return rects
    
    def is_off_screen(self):
        """Check if pipe has left the screen."""
        return self.x + self.width < 0


class FlappyBirdGame:
    """Main game class."""
    
    def __init__(self, screen_width=480, screen_height=320, surface=None, touch_driver=None,
                 character="dino", driver=None, rotate_180: bool = True):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.game_h = screen_height - _STATUS_BAR_H  # game-area height
        self.character = character
        self._driver = driver
        self._use_sdl_display = (surface is None and driver is None)
        self._touch_driver = touch_driver
        self._rotate_180 = rotate_180
        if surface is not None:
            self.surface = surface
        else:
            self.surface = pygame.display.set_mode((screen_width, screen_height))
            pygame.display.set_caption("Flappy Bird")

        # Subsurface views into self.surface (drawing here modifies self.surface in-place)
        self._status_view = self.surface.subsurface((0, 0, screen_width, _STATUS_BAR_H))
        self._game_view = self.surface.subsurface((0, _STATUS_BAR_H, screen_width, self.game_h))

        # Pre-render static background once — reused every frame
        self._bg_surface = pygame.Surface((screen_width, self.game_h))
        self._render_bg()

        self.clock = pygame.time.Clock()
        self.fps = 60

        # Game state
        self.running = True
        self.back_to_menu = False
        self.game_over = False
        self.game_over_at = 0.0
        self.game_over_timeout = 60.0
        self.score = 0
        self.level = 1

        # Touch edge detection — jump only on press, not while holding
        self._prev_touched = False

        # Bird (coordinates are in game-area space: 0..game_h)
        self.bird = Bird(screen_width // 4, self.game_h // 2)

        # Pipes
        self.pipes = []
        self.pipe_spawn_interval_sec = 3.0
        self.pipe_last_spawn_time = time.time() - self.pipe_spawn_interval_sec + 3.0

        # Delta-time tracker for frame-rate-independent pipe movement
        self._last_update_time = time.time()

        # Touch input
        self.last_touch_time = 0
        self.touch_debounce = 0.25

        # Status bar dirty tracking (only repainted when score/level changes)
        self._status_dirty = True
        self._last_status_score = -1
        self._last_status_level = -1

        # Colors
        self.bird_color = (255, 255, 100)
        self.pipe_color = (0, 180, 0)
        self.text_color = (255, 255, 255)
    
    def _render_bg(self) -> None:
        """Pre-render gradient sky + ground strip into _bg_surface (called once)."""
        w, h = self.screen_width, self.game_h
        for y in range(h):
            t = y / h
            pygame.draw.line(self._bg_surface,
                             (int(20 + t * 8), int(55 + t * 25), int(130 - t * 55)),
                             (0, y), (w - 1, y))
        pygame.draw.rect(self._bg_surface, (80, 60, 40), (0, h - 4, w, 4))

    def _draw_status_bar(self) -> None:
        """Paint the HUD: score (left), speed arrows (centre), level (right)."""
        self._status_view.fill((15, 15, 35))
        # Back-to-menu button — visible coloured box on left
        pygame.draw.rect(self._status_view, (60, 60, 130), (2, 3, 46, 29), border_radius=4)
        pygame.draw.rect(self._status_view, (120, 120, 220), (2, 3, 46, 29), 2, border_radius=4)
        btn_font = pygame.font.Font(None, 20)
        btn_txt = btn_font.render("\u25c4MENU", True, (200, 200, 255))
        self._status_view.blit(btn_txt, btn_txt.get_rect(center=(25, 17)))
        font = pygame.font.Font(None, 30)
        # Score
        s = font.render(f"Bars: {self.score}", True, (230, 230, 230))
        self._status_view.blit(s, (56, 6))
        # Level
        l_surf = font.render(f"Lv {self.level}", True, (200, 200, 100))
        self._status_view.blit(l_surf, l_surf.get_rect(topright=(self.screen_width - 8, 6)))
        # Speed arrows (1 per level, max 5, colour shifts red as it speeds up)
        n = min(self.level, 5)
        af = pygame.font.Font(None, 22)
        a = af.render("\u25b6" * n, True, (min(80 + n * 35, 255), max(200 - n * 20, 80), 80))
        self._status_view.blit(a, a.get_rect(center=(self.screen_width // 2, _STATUS_BAR_H // 2)))
        # Separator line
        pygame.draw.line(self._status_view, (50, 50, 80),
                         (0, _STATUS_BAR_H - 1), (self.screen_width - 1, _STATUS_BAR_H - 1))

    def _draw_character(self, surface: pygame.Surface, cx: int, cy: int) -> None:
        """Draw the player character at (cx, cy) in game-area coordinates."""
        if self.character == "dino":
            _draw_dino(surface, cx, cy)
        else:
            pygame.draw.circle(surface, self.bird_color, (cx, cy), self.bird.width // 2)

    def _pipe_speed(self) -> float:
        """Speed increases with level, in px/sec (frame-rate independent)."""
        return min(216.0 + (self.level - 1) * 36.0, 420.0)

    def _pipe_gap(self) -> int:
        """Gap narrows with level (min 100px)."""
        return max(170 - (self.level - 1) * 12, 100)

    def _update_level(self) -> None:
        """Increase level every 3 bars passed."""
        new_level = self.score // 3 + 1
        if new_level > self.level:
            self.level = new_level
            self.pipe_spawn_interval_sec = max(3.0 - (self.level - 1) * 0.15, 1.5)
            # Prevent double-spawn: after shortening interval, wait a full interval
            self.pipe_last_spawn_time = time.time()

    def handle_events(self):
        """Handle pygame events."""
        # Poll touch driver with edge detection — jump only on finger-down, not hold
        if self._touch_driver is not None:
            pressed, rx, ry = self._touch_driver.poll_xy()
            rising_edge = pressed and not self._prev_touched
            self._prev_touched = pressed
            if rising_edge:
                current_time = time.time()
                if current_time - self.last_touch_time > self.touch_debounce:
                    sx, sy = _fb_to_screen(rx, ry, self.screen_width, self.screen_height,
                                           self._rotate_180)
                    if sy < _STATUS_BAR_H and sx < 50:
                        self.back_to_menu = True
                        self.running = False
                    elif self.game_over:
                        self.restart()
                    else:
                        self.bird.jump()
                    self.last_touch_time = current_time

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_SPACE:
                    if self.game_over:
                        self.restart()
                    else:
                        self.bird.jump()
            elif event.type == pygame.MOUSEBUTTONDOWN and self._touch_driver is None:
                # Only use SDL mouse events when no touch driver is available
                current_time = time.time()
                if current_time - self.last_touch_time > self.touch_debounce:
                    if self.game_over:
                        self.restart()
                    else:
                        self.bird.jump()
                    self.last_touch_time = current_time
    
    def spawn_pipe(self):
        """Spawn a new pipe at current level difficulty."""
        gap_height = self._pipe_gap()  # compute first so max_gap_y can use it
        min_gap_y = 30
        max_gap_y = self.game_h - gap_height - 30  # ensure full gap visible in game area

        gap_y = random.randint(min_gap_y, max_gap_y)
        pipe = Pipe(self.screen_width, gap_y, gap_height, self.screen_width, self.game_h)
        pipe.speed = self._pipe_speed()
        self.pipes.append(pipe)
    
    def update(self):
        """Update game state."""
        now = time.time()
        dt = min(now - self._last_update_time, 0.05)  # cap at 50ms to avoid jumps
        self._last_update_time = now

        if self.game_over:
            # Auto-exit after timeout
            if self.game_over_at > 0 and (time.time() - self.game_over_at) >= self.game_over_timeout:
                self.running = False
            return
        
        # Update bird
        self.bird.update()

        # Level progression
        self._update_level()

        # Check bird bounds (falling off screen)
        if self.bird.y > self.game_h or self.bird.y < 0:
            self.game_over = True
            self.game_over_at = time.time()
            return
        
        # Spawn new pipes (time-based)
        _now = time.time()
        if _now - self.pipe_last_spawn_time >= self.pipe_spawn_interval_sec:
            self.spawn_pipe()
            self.pipe_last_spawn_time = _now
        
        # Update and check collisions with pipes
        pipes_to_remove = []
        for pipe in self.pipes:
            pipe.update(dt)
            
            # Check if bird passed pipe (score point)
            if not pipe.passed and pipe.x + pipe.width < self.bird.x:
                pipe.passed = True
                self.score += 1
            
            # Check collision
            bird_rect = self.bird.get_rect()
            for pipe_rect in pipe.get_rects():
                if bird_rect.colliderect(pipe_rect):
                    self.game_over = True
                    self.game_over_at = time.time()
                    return
            
            # Remove pipes off screen
            if pipe.is_off_screen():
                pipes_to_remove.append(pipe)
        
        for pipe in pipes_to_remove:
            self.pipes.remove(pipe)
    
    def draw(self) -> bool:
        """Draw game state. Returns True if present was handled internally."""
        # Status bar — only repaint when score/level changes
        if self.score != self._last_status_score or self.level != self._last_status_level:
            self._draw_status_bar()
            self._last_status_score = self.score
            self._last_status_level = self.level
            self._status_dirty = True

        # Game area — blit pre-rendered background, then game objects
        self._game_view.blit(self._bg_surface, (0, 0))
        for pipe in self.pipes:
            pipe.draw(self._game_view, self.pipe_color)
        self._draw_character(self._game_view, int(self.bird.x), int(self.bird.y))

        # Game over overlay
        if self.game_over:
            overlay = pygame.Surface((self.screen_width, self.game_h))
            overlay.set_alpha(180)
            overlay.fill((0, 0, 0))
            self._game_view.blit(overlay, (0, 0))

            font_big = pygame.font.Font(None, 40)
            go = font_big.render("GAME OVER", True, (255, 80, 80))
            self._game_view.blit(go, go.get_rect(center=(self.screen_width // 2, self.game_h // 2 - 30)))

            font_med = pygame.font.Font(None, 32)
            sc = font_med.render(f"Bars: {self.score}  Lv {self.level}", True, self.text_color)
            self._game_view.blit(sc, sc.get_rect(center=(self.screen_width // 2, self.game_h // 2 + 10)))

            font_sm = pygame.font.Font(None, 24)
            rt = font_sm.render("TAP TO RESTART", True, (200, 200, 200))
            self._game_view.blit(rt, rt.get_rect(center=(self.screen_width // 2, self.game_h // 2 + 45)))

            if self.game_over_at > 0:
                remaining = max(0, self.game_over_timeout - (time.time() - self.game_over_at))
                cd = font_sm.render(f"Auto-exit in {int(remaining)}s", True, (150, 150, 150))
                self._game_view.blit(cd, cd.get_rect(center=(self.screen_width // 2, self.game_h - 16)))

        # Present
        if self._driver is not None:
            if self._status_dirty:
                self._driver.present_rows(0, _STATUS_BAR_H)
                self._status_dirty = False
            self._driver.present_rows(_STATUS_BAR_H, self.screen_height)
            return True
        if self._use_sdl_display:
            pygame.display.flip()
            return True
        return False  # caller must present
    
    def restart(self):
        """Restart the game."""
        self.bird = Bird(self.screen_width // 4, self.game_h // 2)
        self.pipes = []
        self.pipe_spawn_interval_sec = 3.0
        self.pipe_last_spawn_time = time.time() - self.pipe_spawn_interval_sec + 3.0
        self.score = 0
        self.level = 1
        self.game_over = False
        self.game_over_at = 0.0
        self._prev_touched = False
        self._last_update_time = time.time()
        self._status_dirty = True
        self._last_status_score = -1
        self._last_status_level = -1
    
    def run(self):
        """Main game loop."""
        while self.running:
            self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(self.fps)
        
        pygame.quit()


def main():
    """Entry point."""
    pygame.init()
    game = FlappyBirdGame(screen_width=480, screen_height=320)
    game.run()


if __name__ == "__main__":
    main()
