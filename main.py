#!/usr/bin/env python3

import argparse
import fcntl
import os
import signal
import subprocess
import sys
import time

import pygame

from app import FaceApplication
from driver import create_framebuffer_driver, create_sdl_driver, create_touch_driver


WIDTH = 480
HEIGHT = 320
FPS = 30
FB_FPS = 20
IDLE_TIMEOUT_SECONDS = 10 * 60
DEFAULT_CYCLE_INTERVAL_SECONDS = 6
DISPLAY_ROTATE_180 = True
DOUBLE_TAP_WINDOW_SECONDS = 0.70
TOUCH_TAP_DEBOUNCE_SECONDS = 0.08
DOUBLE_TAP_CYCLE_PAUSE_SECONDS = 20.0
RUNTIME_DIR = os.path.join(os.path.dirname(__file__), ".runtime")
LOCK_FILE = os.path.join(RUNTIME_DIR, f"digitalface_{os.getuid()}.lock")
FACE_CONTROL_FILE = os.path.join(RUNTIME_DIR, "digitalface_expression")
FACE_CONTROL_PAUSE_FILE = os.path.join(RUNTIME_DIR, "digitalface_expression_pause_until")
HMI_REQUEST_FILE = os.path.join(RUNTIME_DIR, "digitalface_hmi_request")
HMI_SOCKET_FILE = os.path.join(RUNTIME_DIR, "digitalface_hmi.sock")
HMI_DEFAULT_DURATION_SECONDS = 10
_lock_handle = None


def acquire_single_instance_lock() -> bool:
    global _lock_handle
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    try:
        os.chmod(RUNTIME_DIR, 0o1777)
    except OSError:
        pass
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


GAME_DIR = os.path.join(os.path.dirname(__file__), "games", "flappy_bird")


def launch_game(fbdev: str) -> None:
    """Run Flappy Bird as a subprocess; handle SIGTERM by killing the child."""
    game_main = os.path.join(GAME_DIR, "main.py")
    proc = subprocess.Popen([sys.executable, game_main, "--fbdev", fbdev, "--rotate-180"])

    def _kill_game(sig: int, _frame: object) -> None:
        proc.terminate()
        proc.wait()

    old_sigterm = signal.signal(signal.SIGTERM, _kill_game)
    old_sigint = signal.signal(signal.SIGINT, _kill_game)
    try:
        proc.wait()
    finally:
        signal.signal(signal.SIGTERM, old_sigterm)
        signal.signal(signal.SIGINT, old_sigint)

    # Clear framebuffer to black so the game-over frame doesn't bleed into digitalface
    try:
        with open(fbdev, "rb+") as fb:
            fb.write(b"\x00" * (WIDTH * HEIGHT * 2))
    except OSError:
        pass
    time.sleep(0.15)  # brief pause for visual separation


def handle_tap_for_next_face(app: FaceApplication, now: float, last_tap_at: float) -> tuple[float, bool]:
    """Return (new last_tap_at, launch_game)."""
    if last_tap_at > 0 and (now - last_tap_at) <= DOUBLE_TAP_WINDOW_SECONDS:
        # Double tap → launch game
        return 0.0, True
    return now, False


def run_sdl_mode() -> None:
    driver = create_sdl_driver(WIDTH, HEIGHT, rotate_180=DISPLAY_ROTATE_180)
    app = FaceApplication(driver, FACE_CONTROL_FILE, default_expression="happy", pause_file=FACE_CONTROL_PAUSE_FILE, hmi_request_file=HMI_REQUEST_FILE, hmi_socket_file=HMI_SOCKET_FILE, hmi_default_duration=HMI_DEFAULT_DURATION_SECONDS)
    clock = pygame.time.Clock()
    last_tap_at = 0.0
    last_touch_at = time.time()
    display_sleeping = False
    running = True
    while running:
        now = time.time()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                last_touch_at = now
                if display_sleeping:
                    driver.set_led_enabled(True)
                    display_sleeping = False
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
            elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                last_touch_at = now
                if display_sleeping:
                    driver.set_led_enabled(True)
                    display_sleeping = False
                if app.hmi_text is not None:
                    app.dismiss_hmi()
                else:
                    last_tap_at, _ = handle_tap_for_next_face(app, now, last_tap_at)

        app.update(now)
        app.consume_display_changed()

        if IDLE_TIMEOUT_SECONDS is not None and (now - last_touch_at) >= IDLE_TIMEOUT_SECONDS and not display_sleeping:
            driver.set_led_enabled(False)
            display_sleeping = True

        if app.hmi_text is not None and now < app.hmi_until and display_sleeping:
            driver.set_led_enabled(True)
            display_sleeping = False
            last_touch_at = now

        if not display_sleeping:
            app.render(now)
            driver.present()
        clock.tick(FPS)

    app.close()
    driver.close()


def run_framebuffer_mode(fbdev: str) -> None:
    while True:  # outer loop: restart display after game exits
        driver = create_framebuffer_driver(fbdev, WIDTH, HEIGHT, rotate_180=DISPLAY_ROTATE_180)
        touch = create_touch_driver()
        app = FaceApplication(driver, FACE_CONTROL_FILE, default_expression="happy", pause_file=FACE_CONTROL_PAUSE_FILE, hmi_request_file=HMI_REQUEST_FILE, hmi_socket_file=HMI_SOCKET_FILE, hmi_default_duration=HMI_DEFAULT_DURATION_SECONDS)
        clock = pygame.time.Clock()
        last_tap_at = 0.0
        last_touch_tap_event_at = 0.0
        last_touch_at = time.time()
        display_sleeping = False
        running = True
        game_requested = False

        def stop_handler(_sig: int, _frame: object) -> None:
            nonlocal running
            running = False

        signal.signal(signal.SIGINT, stop_handler)
        signal.signal(signal.SIGTERM, stop_handler)

        try:
            while running:
                now = time.time()
                touch_down = touch.poll()
                if touch_down and (now - last_touch_tap_event_at) >= TOUCH_TAP_DEBOUNCE_SECONDS:
                    last_touch_at = now
                    if display_sleeping:
                        driver.set_led_enabled(True)
                        display_sleeping = False
                    if app.hmi_text is not None:
                        app.dismiss_hmi()
                    else:
                        last_tap_at, game_requested = handle_tap_for_next_face(app, now, last_tap_at)
                        if game_requested:
                            running = False
                    last_touch_tap_event_at = now

                app.update(now)
                app.consume_display_changed()

                if IDLE_TIMEOUT_SECONDS is not None and (now - last_touch_at) >= IDLE_TIMEOUT_SECONDS and not display_sleeping:
                    driver.set_led_enabled(False)
                    display_sleeping = True

                if app.hmi_text is not None and now < app.hmi_until and display_sleeping:
                    driver.set_led_enabled(True)
                    display_sleeping = False
                    last_touch_at = now

                if not display_sleeping:
                    app.render(now)
                    driver.present()
                clock.tick(FB_FPS)
        finally:
            app.close()
            touch.close()
            driver.close()

        if game_requested:
            launch_game(fbdev)
            if not running:
                break  # SIGTERM arrived during game → exit cleanly
            # loop back → reinitialize display and resume digitalface
        else:
            break  # clean exit (SIGTERM/SIGINT)


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
