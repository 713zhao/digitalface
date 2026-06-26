#!/usr/bin/env python3
"""Flappy Bird launcher for framebuffer display."""

import os
import sys
import pygame

# Add digitalface root to path so we can import the display/touch drivers
_GAME_DIR = os.path.dirname(os.path.abspath(__file__))
_DIGITALFACE_DIR = os.path.dirname(os.path.dirname(_GAME_DIR))
sys.path.insert(0, _DIGITALFACE_DIR)

from game import FlappyBirdGame


def run_framebuffer_mode(fbdev="/dev/fb1", rotate_180=False):
    """Run game directly on framebuffer using the digitalface display/touch drivers."""
    from driver.display_driver import FramebufferPresenter, TouchDriver

    # Use offscreen SDL driver for keyboard events only (no display window needed)
    os.environ["SDL_VIDEODRIVER"] = "offscreen"

    pygame.font.init()
    pygame.display.init()

    try:
        presenter = FramebufferPresenter(fbdev, 480, 320)
    except OSError as e:
        print(f"\n⚠️  Cannot open framebuffer {fbdev}: {e}")
        print("\nMake sure digitalface is stopped first:")
        print("   sudo systemctl stop digitalface")
        sys.exit(1)

    touch = TouchDriver()
    surface = pygame.Surface((480, 320))
    game = FlappyBirdGame(screen_width=480, screen_height=320, surface=surface, touch_driver=touch)
    clock = pygame.time.Clock()

    try:
        while game.running:
            game.handle_events()
            game.update()
            game.draw()
            frame = pygame.transform.flip(surface, True, True) if rotate_180 else surface
            presenter.present(frame)
            clock.tick(60)
    finally:
        presenter.close()
        touch.close()

    # Clear screen, then exec back to digitalface (same PID — no systemd restart gap)
    try:
        with open(fbdev, "rb+") as fb:
            fb.write(b"\x00" * (480 * 320 * 2))
    except OSError:
        pass
    time.sleep(0.05)
    digitalface_main = os.path.join(_DIGITALFACE_DIR, "main.py")
    os.execv(sys.executable, [sys.executable, digitalface_main, "--force-fb", "--fbdev", fbdev])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Flappy Bird Game")
    parser.add_argument("--fbdev", default="/dev/fb1", help="Framebuffer device (default: /dev/fb1)")
    parser.add_argument("--rotate-180", action="store_true", help="Rotate display 180 degrees")
    args = parser.parse_args()

    run_framebuffer_mode(args.fbdev, rotate_180=args.rotate_180)
