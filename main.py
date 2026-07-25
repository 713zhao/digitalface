#!/usr/bin/env python3

import argparse
import fcntl
import os
import signal
import subprocess
import time

import pygame

from app import DashboardApp, FaceApplication
from driver import create_framebuffer_driver, create_sdl_driver, create_touch_driver, touch_to_screen


WIDTH = 480
HEIGHT = 320
FPS = 30
FB_FPS = 20
# Home screen = Smart Home dashboard. After DASHBOARD_IDLE_TIMEOUT_SECONDS of no
# touch, it falls back to the animated face as an idle screensaver. After
# BLACKSCREEN_IDLE_TIMEOUT_SECONDS (measured from that same last-touch clock)
# the backlight is turned off entirely (black screen).
DASHBOARD_IDLE_TIMEOUT_SECONDS = 10 * 60
BLACKSCREEN_IDLE_TIMEOUT_SECONDS = 60 * 60
MENU_IDLE_TIMEOUT_SECONDS = 60
DEFAULT_CYCLE_INTERVAL_SECONDS = 6
DISPLAY_ROTATE_180 = True
# Touch calibration for ADS7846/XPT2046 on this RPi 3.5" LCD.
# Measured interactively 2026-06-28: corners (TL/TR/BL/BR) gave:
#   TL=(413,3562)  TR=(3721,3596)  BL=(307,324)  BR=(3819,368)
# ABS_Y is INVERTED on this display (high value at physical top, low at bottom).
# These are used as os.environ defaults so the service env can still override.
# NOTE: the corners above were touched as they visually appear on the mounted
# screen (i.e. already in the post-DISPLAY_ROTATE_180 orientation), so the
# raw->pixel mapping in touch_to_screen() already lands on the correct on-screen
# spot. TOUCH_ROTATE_180 must stay False, otherwise touch_to_screen() mirrors
# an already-correct point a second time (touch left -> registers on the
# right, touch top -> registers on the bottom).
TOUCH_ROTATE_180 = False
# Full ADC range (12-bit = 0-4095).
# ADS7846 Y axis is physically inverted on this panel (high raw = physical top),
# so Y_MIN > Y_MAX to flip it.
TOUCH_X_MIN = 0
TOUCH_X_MAX = 4095
TOUCH_Y_MIN = 4095   # inverted: high raw value = physical top
TOUCH_Y_MAX = 0      # inverted: low raw value  = physical bottom
DOUBLE_TAP_WINDOW_SECONDS = 0.70
TOUCH_TAP_DEBOUNCE_SECONDS = 0.08
DOUBLE_TAP_CYCLE_PAUSE_SECONDS = 20.0
RUNTIME_DIR = os.path.join(os.path.dirname(__file__), ".runtime")
LOCK_FILE = os.path.join(RUNTIME_DIR, f"digitalface_{os.getuid()}.lock")
FACE_CONTROL_FILE = os.path.join(RUNTIME_DIR, "digitalface_expression")
FACE_CONTROL_PAUSE_FILE = os.path.join(RUNTIME_DIR, "digitalface_expression_pause_until")
HMI_REQUEST_FILE = os.path.join(RUNTIME_DIR, "digitalface_hmi_request")
HMI_SOCKET_FILE = os.path.join(RUNTIME_DIR, "digitalface_hmi.sock")
HMI_STATUS_FILE = os.path.join(RUNTIME_DIR, "digitalface_hmi_status.json")
HMI_DEFAULT_DURATION_SECONDS = 10
# Touch this file (e.g. from a voice assistant integration) to jump straight
# to the Smart Home dashboard screen from the face screen.
DASHBOARD_SHOW_REQUEST_FILE = os.path.join(RUNTIME_DIR, "digitalface_show_dashboard")
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


import importlib.util as _ilu


def _load_game_module(rel_path: str, module_name: str):
    path = os.path.join(os.path.dirname(__file__), rel_path)
    spec = _ilu.spec_from_file_location(module_name, path)
    mod = _ilu.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


FlappyBirdGame = _load_game_module("games/flappy_bird/game.py",   "flappy_game").FlappyBirdGame
GameMenu       = _load_game_module("games/menu.py",               "games_menu").GameMenu
SnakeGame      = _load_game_module("games/snake/snake.py",        "snake_game").SnakeGame
BreakoutGame   = _load_game_module("games/breakout/breakout.py",  "breakout_game").BreakoutGame


def _create_game(key: str, driver, touch):
    kwargs = dict(
        screen_width=WIDTH,
        screen_height=HEIGHT,
        surface=driver.surface,
        touch_driver=touch,
        driver=driver,
        rotate_180=TOUCH_ROTATE_180,
    )
    if key == "snake":
        return SnakeGame(**kwargs)
    if key == "breakout":
        return BreakoutGame(**kwargs)
    return FlappyBirdGame(**kwargs)


def run_sdl_mode() -> None:
    driver = create_sdl_driver(WIDTH, HEIGHT, rotate_180=DISPLAY_ROTATE_180)
    app = FaceApplication(driver, FACE_CONTROL_FILE, default_expression="happy", pause_file=FACE_CONTROL_PAUSE_FILE, hmi_request_file=HMI_REQUEST_FILE, hmi_socket_file=HMI_SOCKET_FILE, hmi_default_duration=HMI_DEFAULT_DURATION_SECONDS, hmi_status_file=HMI_STATUS_FILE)
    dashboard = DashboardApp(driver, RUNTIME_DIR, rotate_180=DISPLAY_ROTATE_180)
    # Home screen = dashboard. "face" is the idle screensaver reached after
    # DASHBOARD_IDLE_TIMEOUT_SECONDS of inactivity. "menu"/"game" are reached
    # via the dashboard's Games quick-control.
    mode = "dashboard"
    menu = None
    game = None
    clock = pygame.time.Clock()
    last_touch_at = time.time()
    display_sleeping = False
    running = True
    while running:
        now = time.time()
        idle_seconds = now - last_touch_at

        if mode == "dashboard" and idle_seconds >= DASHBOARD_IDLE_TIMEOUT_SECONDS:
            mode = "face"

        if mode in ("menu", "game"):
            if mode == "game":
                assert game is not None
                game.handle_events()
                game.update()
                if not game.draw():
                    driver.present()
                if not game.running:
                    back_to_menu = getattr(game, "back_to_menu", False)
                    game = None
                    driver.surface.fill((0, 0, 0))
                    driver.present()
                    last_touch_at = now
                    if back_to_menu:
                        menu = GameMenu(screen_width=WIDTH, screen_height=HEIGHT, surface=driver.surface,
                                        touch_driver=None, driver=driver, rotate_180=DISPLAY_ROTATE_180)
                        mode = "menu"
                    else:
                        mode = "dashboard"
                clock.tick(60)
            else:
                assert menu is not None
                menu.handle_events()
                if not menu.draw():
                    driver.present()
                if not menu.running:
                    chosen = menu.selected
                    menu = None
                    driver.surface.fill((0, 0, 0))
                    driver.present()
                    last_touch_at = now
                    if chosen and chosen != "dashboard":
                        game = _create_game(chosen, driver, None)
                        mode = "game"
                    else:
                        mode = "dashboard"
                clock.tick(30)
            continue

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
                elif event.key == pygame.K_d:
                    # Dev convenience: toggle between home (dashboard) and idle (face).
                    mode = "face" if mode == "dashboard" else "dashboard"
            elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
                last_touch_at = now
                if display_sleeping:
                    driver.set_led_enabled(True)
                    display_sleeping = False
                if mode == "dashboard":
                    sx, sy = event.pos if event.type == pygame.MOUSEBUTTONDOWN else (
                        int(event.x * WIDTH), int(event.y * HEIGHT))
                    result = dashboard.handle_touch_tap(sx, sy, now)
                    if result == "games":
                        menu = GameMenu(screen_width=WIDTH, screen_height=HEIGHT, surface=driver.surface,
                                        touch_driver=None, driver=driver, rotate_180=DISPLAY_ROTATE_180)
                        driver.surface.fill((0, 0, 0))
                        driver.present()
                        mode = "menu"
                elif app.hmi_text is not None:
                    app.dismiss_hmi()
                else:
                    # Any tap on the idle screen wakes back to the dashboard (home).
                    mode = "dashboard"

        if mode == "dashboard":
            dashboard.update(now)
            if idle_seconds >= BLACKSCREEN_IDLE_TIMEOUT_SECONDS and not display_sleeping:
                driver.set_led_enabled(False)
                display_sleeping = True
            if not display_sleeping:
                dashboard.render(now)
                driver.present()
            clock.tick(FPS)
            continue

        # mode == "face" (idle screensaver)
        app.update(now)
        app.consume_display_changed()

        if idle_seconds >= BLACKSCREEN_IDLE_TIMEOUT_SECONDS and not display_sleeping:
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
    # Enable SDL offscreen driver so keyboard events work in game mode
    os.environ.setdefault("SDL_VIDEODRIVER", "offscreen")
    # Apply touch calibration defaults (service env vars take priority)
    os.environ.setdefault("DIGITALFACE_TOUCH_X_MIN", str(TOUCH_X_MIN))
    os.environ.setdefault("DIGITALFACE_TOUCH_X_MAX", str(TOUCH_X_MAX))
    os.environ.setdefault("DIGITALFACE_TOUCH_Y_MIN", str(TOUCH_Y_MIN))
    os.environ.setdefault("DIGITALFACE_TOUCH_Y_MAX", str(TOUCH_Y_MAX))
    pygame.display.init()

    driver = create_framebuffer_driver(fbdev, WIDTH, HEIGHT, rotate_180=DISPLAY_ROTATE_180)
    touch = create_touch_driver()
    app = FaceApplication(driver, FACE_CONTROL_FILE, default_expression="happy", pause_file=FACE_CONTROL_PAUSE_FILE, hmi_request_file=HMI_REQUEST_FILE, hmi_socket_file=HMI_SOCKET_FILE, hmi_default_duration=HMI_DEFAULT_DURATION_SECONDS, hmi_status_file=HMI_STATUS_FILE)
    dashboard = DashboardApp(driver, RUNTIME_DIR, rotate_180=TOUCH_ROTATE_180)
    clock = pygame.time.Clock()
    last_touch_tap_event_at = 0.0
    last_touch_at = time.time()
    display_sleeping = False
    running = True

    # Mode: "dashboard" (home, default), "face" (idle screensaver), "menu", or "game".
    mode = "dashboard"
    game = None
    menu = None
    dash_prev_touched = False
    dash_last_touch_event_at = 0.0
    dash_last_tap_at = 0.0
    next_dashboard_request_poll_at = 0.0

    def stop_handler(_sig: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    try:
        while running:
            now = time.time()
            idle_seconds = now - last_touch_at

            # Home (dashboard) falls back to the animated face as an idle
            # screensaver after DASHBOARD_IDLE_TIMEOUT_SECONDS of inactivity.
            if mode == "dashboard" and idle_seconds >= DASHBOARD_IDLE_TIMEOUT_SECONDS:
                mode = "face"

            if mode == "face" and now >= next_dashboard_request_poll_at:
                next_dashboard_request_poll_at = now + 0.5
                if os.path.exists(DASHBOARD_SHOW_REQUEST_FILE):
                    try:
                        os.remove(DASHBOARD_SHOW_REQUEST_FILE)
                    except OSError:
                        pass
                    driver.surface.fill((0, 0, 0))
                    driver.present()
                    mode = "dashboard"
                    last_touch_at = now
                    continue

            if mode == "game":
                # ── Game mode ────────────────────────────────────────────
                assert game is not None
                game.handle_events()
                game.update()
                if not game.draw():  # game.draw() returns True if it handled present
                    driver.present()
                clock.tick(60)

                if not game.running:
                    back_to_menu = getattr(game, 'back_to_menu', False)
                    game = None
                    driver.surface.fill((0, 0, 0))
                    driver.present()
                    last_touch_at = now  # reset idle timer
                    if back_to_menu:
                        menu = GameMenu(
                            screen_width=WIDTH, screen_height=HEIGHT,
                            surface=driver.surface, touch_driver=touch,
                            driver=driver, rotate_180=TOUCH_ROTATE_180,
                        )
                        mode = "menu"
                    else:
                        mode = "dashboard"

            elif mode == "menu":
                # ── Menu mode ────────────────────────────────────────────
                assert menu is not None
                menu.handle_events()
                if not menu.draw():
                    driver.present()
                clock.tick(30)

                if (now - menu._last_touch_time) >= MENU_IDLE_TIMEOUT_SECONDS:
                    menu = None
                    driver.surface.fill((0, 0, 0))
                    driver.present()
                    mode = "dashboard"
                    last_touch_at = now
                    continue

                if not menu.running:
                    chosen = menu.selected
                    menu = None
                    driver.surface.fill((0, 0, 0))
                    driver.present()
                    if chosen and chosen != "dashboard":
                        game = _create_game(chosen, driver, touch)
                        mode = "game"
                    else:
                        mode = "dashboard"
                    last_touch_at = now

            elif mode == "dashboard":
                # ── Dashboard mode (home) ──────────────────────────────────
                pressed, rx, ry = touch.poll_xy()
                rising = pressed and not dash_prev_touched
                dash_prev_touched = pressed

                if rising and (now - dash_last_touch_event_at) >= TOUCH_TAP_DEBOUNCE_SECONDS:
                    dash_last_touch_event_at = now
                    last_touch_at = now
                    if display_sleeping:
                        driver.set_led_enabled(True)
                        display_sleeping = False

                    double_tap = dash_last_tap_at > 0 and (now - dash_last_tap_at) <= DOUBLE_TAP_WINDOW_SECONDS
                    dash_last_tap_at = 0.0 if double_tap else now

                    if double_tap:
                        # Double tap → manually jump to the idle face screen.
                        driver.surface.fill((0, 0, 0))
                        driver.present()
                        mode = "face"
                        last_touch_at = now
                    else:
                        sx, sy = touch_to_screen(rx, ry, WIDTH, HEIGHT, TOUCH_ROTATE_180)
                        result = dashboard.handle_touch_tap(sx, sy, now)
                        if result == "games":
                            driver.surface.fill((0, 0, 0))
                            driver.present()
                            menu = GameMenu(
                                screen_width=WIDTH, screen_height=HEIGHT,
                                surface=driver.surface, touch_driver=touch,
                                driver=driver, rotate_180=TOUCH_ROTATE_180,
                            )
                            mode = "menu"
                            last_touch_at = now

                if mode == "dashboard":
                    dashboard.update(now)

                    if idle_seconds >= BLACKSCREEN_IDLE_TIMEOUT_SECONDS and not display_sleeping:
                        driver.set_led_enabled(False)
                        display_sleeping = True

                    if not display_sleeping:
                        dashboard.render(now)
                        driver.present()
                    clock.tick(FB_FPS)

            elif mode == "face":
                # ── Face mode (idle screensaver) ──────────────────────────
                touch_down = touch.poll()
                if touch_down and (now - last_touch_tap_event_at) >= TOUCH_TAP_DEBOUNCE_SECONDS:
                    last_touch_at = now
                    if display_sleeping:
                        driver.set_led_enabled(True)
                        display_sleeping = False
                    if app.hmi_text is not None:
                        app.dismiss_hmi()
                    else:
                        # Any tap on the idle screen wakes back to the dashboard (home).
                        mode = "dashboard"
                    last_touch_tap_event_at = now

                if mode == "face":
                    app.update(now)
                    app.consume_display_changed()

                    if idle_seconds >= BLACKSCREEN_IDLE_TIMEOUT_SECONDS and not display_sleeping:
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
