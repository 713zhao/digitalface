#!/usr/bin/env python3

import argparse
import fcntl
import os
import signal
import subprocess
import time

import pygame

from app import FaceApplication
from driver import create_framebuffer_driver, create_sdl_driver, create_touch_driver


WIDTH = 480
HEIGHT = 320
FPS = 30
FB_FPS = 8
IDLE_TIMEOUT_SECONDS = None
DEFAULT_CYCLE_INTERVAL_SECONDS = 6
RUNTIME_DIR = os.path.join(os.path.dirname(__file__), ".runtime")
LOCK_FILE = os.path.join(RUNTIME_DIR, f"digitalface_{os.getuid()}.lock")
FACE_CONTROL_FILE = os.path.join(RUNTIME_DIR, "digitalface_expression")
_lock_handle = None


def acquire_single_instance_lock() -> bool:
    global _lock_handle
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    _lock_handle = open(LOCK_FILE, "w")
    try:
        fcntl.flock(_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_handle.write(str(os.getpid()))
        _lock_handle.flush()
        return True
    except BlockingIOError:
        return False


def ensure_default_face_cycle() -> None:
    script_path = os.path.join(os.path.dirname(__file__), "cycle_faces_bg.sh")
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    if not os.path.exists(script_path):
        return
    try:
        subprocess.run(
            [script_path, str(DEFAULT_CYCLE_INTERVAL_SECONDS)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return


def run_sdl_mode() -> None:
    driver = create_sdl_driver(WIDTH, HEIGHT)
    app = FaceApplication(driver, FACE_CONTROL_FILE, default_expression="happy")
    clock = pygame.time.Clock()
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
                    app.set_expression("neutral")
                elif event.key == pygame.K_2:
                    app.set_expression("happy")
                elif event.key == pygame.K_3:
                    app.set_expression("listening")
                elif event.key == pygame.K_4:
                    app.set_expression("surprised")

        app.update(now)
        app.consume_display_changed()
        app.render(now)
        driver.present()
        clock.tick(FPS)

    driver.close()


def run_framebuffer_mode(fbdev: str) -> None:
    driver = create_framebuffer_driver(fbdev, WIDTH, HEIGHT)
    touch = create_touch_driver()
    app = FaceApplication(driver, FACE_CONTROL_FILE, default_expression="happy")
    clock = pygame.time.Clock()
    running = True

    def stop_handler(_sig: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    try:
        while running:
            now = time.time()
            touch.poll()

            app.update(now)
            app.consume_display_changed()
            app.render(now)
            driver.present()
            clock.tick(FB_FPS)
    finally:
        touch.close()
        driver.close()


def main() -> None:
    if not acquire_single_instance_lock():
        print("digitalface is already running; exiting second instance")
        return

    ensure_default_face_cycle()

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
