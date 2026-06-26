#!/usr/bin/env python3
"""Flappy Bird launcher for framebuffer display."""

import os
import sys
import pygame
from game import FlappyBirdGame


def run_framebuffer_mode(fbdev="/dev/fb1"):
    """Run game on framebuffer with fallback to SDL."""
    os.environ["SDL_VIDEODRIVER"] = "fbcon"
    os.environ["SDL_FBDEV"] = fbdev
    os.environ["SDL_MOUSEDRV"] = "TSLIB"
    os.environ["SDL_MOUSEDEV"] = "/dev/input/event1"
    
    try:
        pygame.init()
        game = FlappyBirdGame(screen_width=480, screen_height=320)
        game.run()
    except pygame.error as e:
        print(f"\n⚠️  Framebuffer error: {e}")
        print("\n📌 SOLUTION: Stop digitalface first, then run the game:")
        print("   sudo systemctl stop digitalface")
        print("   /home/eric/projects/digitalface/games/flappy_bird/launch.sh")
        print("\nOR run in SDL window mode for testing:")
        print("   /home/eric/projects/digitalface/games/flappy_bird/launch.sh --sdl")
        sys.exit(1)


def run_sdl_mode():
    """Run game in SDL window (for testing)."""
    pygame.init()
    game = FlappyBirdGame(screen_width=480, screen_height=320)
    game.run()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Flappy Bird Game")
    parser.add_argument("--fbdev", default="/dev/fb1", help="Framebuffer device (default: /dev/fb1)")
    parser.add_argument("--sdl", action="store_true", help="Use SDL window instead of framebuffer")
    args = parser.parse_args()
    
    if args.sdl:
        print("🎮 Running in SDL window mode (for testing)")
        run_sdl_mode()
    else:
        run_framebuffer_mode(args.fbdev)
