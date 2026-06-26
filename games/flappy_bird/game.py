#!/usr/bin/env python3
"""Flappy Bird Game - Touch screen controlled."""

import math
import random
import time
import pygame


class Bird:
    """Player bird sprite."""
    
    def __init__(self, x, y, width=20, height=20):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.velocity = 0
        self.gravity = 0.6
        self.jump_power = -12
        self.max_fall_speed = 15
    
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
        self.speed = 5
        self.passed = False
    
    def update(self):
        """Move pipe left."""
        self.x -= self.speed
    
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
    
    def __init__(self, screen_width=480, screen_height=320, surface=None, touch_driver=None):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._use_sdl_display = (surface is None)
        self._touch_driver = touch_driver
        if surface is not None:
            self.surface = surface
        else:
            self.surface = pygame.display.set_mode((screen_width, screen_height))
            pygame.display.set_caption("Flappy Bird")
        
        self.clock = pygame.time.Clock()
        self.fps = 60
        
        # Game state
        self.running = True
        self.game_over = False
        self.score = 0
        
        # Bird
        self.bird = Bird(self.screen_width // 4, self.screen_height // 2)
        
        # Pipes
        self.pipes = []
        self.pipe_spawn_timer = 0
        self.pipe_spawn_interval = 120  # frames
        
        # Touch input
        self.last_touch_time = 0
        self.touch_debounce = 0.1  # seconds
        
        # Colors
        self.bg_color = (20, 30, 60)
        self.bird_color = (255, 255, 100)
        self.pipe_color = (0, 200, 0)
        self.text_color = (255, 255, 255)
    
    def handle_events(self):
        """Handle pygame events."""
        # Poll touch driver (direct evdev) if available
        if self._touch_driver is not None:
            if self._touch_driver.poll():
                current_time = time.time()
                if current_time - self.last_touch_time > self.touch_debounce:
                    if self.game_over:
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
        """Spawn a new pipe."""
        min_gap_y = 50
        max_gap_y = self.screen_height - 100
        gap_height = 120
        
        gap_y = random.randint(min_gap_y, max_gap_y)
        pipe = Pipe(self.screen_width, gap_y, gap_height, self.screen_width, self.screen_height)
        self.pipes.append(pipe)
    
    def update(self):
        """Update game state."""
        if self.game_over:
            return
        
        # Update bird
        self.bird.update()
        
        # Check bird bounds (falling off screen)
        if self.bird.y > self.screen_height or self.bird.y < 0:
            self.game_over = True
            return
        
        # Spawn new pipes
        self.pipe_spawn_timer += 1
        if self.pipe_spawn_timer >= self.pipe_spawn_interval:
            self.spawn_pipe()
            self.pipe_spawn_timer = 0
        
        # Update and check collisions with pipes
        pipes_to_remove = []
        for pipe in self.pipes:
            pipe.update()
            
            # Check if bird passed pipe (score point)
            if not pipe.passed and pipe.x + pipe.width < self.bird.x:
                pipe.passed = True
                self.score += 1
            
            # Check collision
            bird_rect = self.bird.get_rect()
            for pipe_rect in pipe.get_rects():
                if bird_rect.colliderect(pipe_rect):
                    self.game_over = True
                    return
            
            # Remove pipes off screen
            if pipe.is_off_screen():
                pipes_to_remove.append(pipe)
        
        for pipe in pipes_to_remove:
            self.pipes.remove(pipe)
    
    def draw(self):
        """Draw game state."""
        self.surface.fill(self.bg_color)
        
        # Draw bird
        self.bird.draw(self.surface, self.bird_color)
        
        # Draw pipes
        for pipe in self.pipes:
            pipe.draw(self.surface, self.pipe_color)
        
        # Draw score
        font = pygame.font.Font(None, 48)
        score_text = font.render(str(self.score), True, self.text_color)
        self.surface.blit(score_text, (10, 10))
        
        # Draw game over message
        if self.game_over:
            overlay = pygame.Surface((self.screen_width, self.screen_height))
            overlay.set_alpha(200)
            overlay.fill((0, 0, 0))
            self.surface.blit(overlay, (0, 0))
            
            game_over_font = pygame.font.Font(None, 40)
            game_over_text = game_over_font.render("GAME OVER", True, (255, 0, 0))
            game_over_rect = game_over_text.get_rect(center=(self.screen_width // 2, self.screen_height // 2 - 40))
            self.surface.blit(game_over_text, game_over_rect)
            
            score_font = pygame.font.Font(None, 32)
            final_score_text = score_font.render(f"Score: {self.score}", True, self.text_color)
            score_rect = final_score_text.get_rect(center=(self.screen_width // 2, self.screen_height // 2 + 10))
            self.surface.blit(final_score_text, score_rect)
            
            restart_font = pygame.font.Font(None, 24)
            restart_text = restart_font.render("TAP TO RESTART", True, self.text_color)
            restart_rect = restart_text.get_rect(center=(self.screen_width // 2, self.screen_height // 2 + 50))
            self.surface.blit(restart_text, restart_rect)
        
        if self._use_sdl_display:
            pygame.display.flip()
    
    def restart(self):
        """Restart the game."""
        self.bird = Bird(self.screen_width // 4, self.screen_height // 2)
        self.pipes = []
        self.pipe_spawn_timer = 0
        self.score = 0
        self.game_over = False
    
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
