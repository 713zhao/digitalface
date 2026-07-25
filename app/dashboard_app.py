#!/usr/bin/env python3
"""Application layer: Smart Home Command Center dashboard.

Implements the rotating-page dashboard UI described in the project's
Smart Home Command Center design doc:

  - Status bar (time, WiFi, MQTT, indoor temperature)
  - Reminder / News / Voice Assistant / Quick Controls (home page)
  - Dedicated Reminder page (today's full reminder list)
  - Dedicated News page (full headline list)
  - Weather page
  - Energy page
  - Security page
  - Settings screen (toggle page auto-rotation on/off)

Data is read from a JSON file (``dashboard_data.json`` in the runtime
directory) so external integrations (Home Assistant, MQTT bridges,
news fetchers, ...) can update it without touching this module. When the
file is absent or invalid, built-in demo data is shown so the UI is
always presentable.

The reminder card is instead fed live from the aireminder project's MCP
HTTP server (``get_today_reminders`` tool, http://127.0.0.1:8000 by
default), polled periodically. If that server is unreachable, the
dashboard falls back to whatever reminder data came from
``dashboard_data.json``/demo data.

Quick-control taps are written to ``dashboard_action.json`` for an
external automation layer to consume. The voice assistant panel can be
driven externally via a small text control file
(``digitalface_voice_state``) and also supports a local tap-to-demo
cycle (idle -> listening -> processing -> response) for testing without
any backend wired up.

All drawing goes through the ``DisplayDriver`` primitives, matching the
driver/application separation described in interfaces.md.
"""

import copy
import html
import json
import math
import os
import re
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

import pygame

from driver.display_driver import DisplayDriver


# An event/reminder is considered "on" (active, happening now) from its due
# time until this many minutes afterwards. While active, the reminder blinks
# and triggers a spoken sound alert once.
EVENT_ACTIVE_WINDOW_MINUTES = 30

PAGE_HOME = 0
PAGE_REMINDER = 1
PAGE_NEWS = 2
PAGE_WEATHER = 3
PAGE_ENERGY = 4
PAGE_SECURITY = 5
PAGE_COUNT = 6

DEMO_DATA = {
    "status": {"wifi": True, "mqtt": True, "indoor_temp_c": 26},
    "reminder": {"id": "demo-1", "title": "Team Meeting", "time": "09:00 AM", "urgent": False, "active": False},
    "reminders": [
        {"id": "demo-1", "title": "Team Meeting", "time": "09:00 AM", "urgent": False, "active": False},
    ],
    "news": [
        {"category": "AI", "title": "AI automation growing rapidly",
         "summary": "Demo headline shown when no live news feed is reachable."},
        {"category": "Tech", "title": "New energy-saving technology unveiled",
         "summary": "Demo headline shown when no live news feed is reachable."},
        {"category": "Weather", "title": "Weather advisory issued for the region",
         "summary": "Demo headline shown when no live news feed is reachable."},
    ],
    "weather": {"temp_c": 26, "condition": "Clear", "humidity": 55, "forecast": "Sunny tomorrow"},
    "energy": {"usage_kw": 1.2, "solar_kw": 0.8, "battery_pct": 76},
    "security": {
        "door_sensors": {"Front Door": "closed", "Back Door": "closed"},
        "window_sensors": {"Living Room": "closed", "Bedroom": "closed"},
        "cameras": "OK",
    },
}


def _deep_update(base: dict, overrides: dict) -> None:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value


# ── vector icon helpers (avoid depending on emoji glyph support) ───────────


def _icon_bell(driver: DisplayDriver, cx: int, cy: int, r: int, color) -> None:
    driver.arc(color, pygame.Rect(cx - r, cy - r, r * 2, r * 2), math.pi, 2 * math.pi, 2)
    driver.line(color, (cx - r, cy), (cx - r + 2, cy + r - 2), 2)
    driver.line(color, (cx + r, cy), (cx + r - 2, cy + r - 2), 2)
    driver.line(color, (cx - r + 2, cy + r - 2), (cx + r - 2, cy + r - 2), 2)
    driver.circle(color, (cx, cy + r + 3), 2)


def _icon_newspaper(driver: DisplayDriver, cx: int, cy: int, r: int, color) -> None:
    rect = pygame.Rect(cx - r, cy - r + 2, r * 2, r * 2 - 4)
    driver.rect(color, rect, 2)
    for i in range(3):
        y = rect.top + 4 + i * 5
        driver.line(color, (rect.left + 4, y), (rect.right - 4, y), 1)


def _icon_mic(driver: DisplayDriver, cx: int, cy: int, r: int, color) -> None:
    body = pygame.Rect(cx - r // 2, cy - r, r, int(r * 1.4))
    driver.rect(color, body, 0)
    driver.arc(color, pygame.Rect(cx - r, cy - r // 3, r * 2, r * 2), 0, math.pi, 2)
    driver.line(color, (cx, cy + r), (cx, cy + r + 6), 2)
    driver.line(color, (cx - 6, cy + r + 6), (cx + 6, cy + r + 6), 2)


def _icon_bulb(driver: DisplayDriver, cx: int, cy: int, r: int, color) -> None:
    driver.circle(color, (cx, cy - 2), r, 2)
    driver.rect(color, pygame.Rect(cx - r // 2, cy + r - 4, r, 6), 2)
    driver.line(color, (cx - 3, cy - 2), (cx + 3, cy - 2), 1)
    driver.line(color, (cx - 3, cy + 1), (cx + 3, cy + 1), 1)


def _icon_snowflake(driver: DisplayDriver, cx: int, cy: int, r: int, color) -> None:
    for i in range(3):
        ang = math.radians(60 * i)
        dx, dy = math.cos(ang) * r, math.sin(ang) * r
        driver.line(color, (int(cx - dx), int(cy - dy)), (int(cx + dx), int(cy + dy)), 2)


def _icon_lock(driver: DisplayDriver, cx: int, cy: int, r: int, color) -> None:
    body = pygame.Rect(cx - r, cy - 1, r * 2, r + 2)
    driver.rect(color, body, 2)
    driver.arc(color, pygame.Rect(cx - r + 3, cy - r - 3, r * 2 - 6, r * 2), math.pi, 2 * math.pi, 2)
    driver.circle(color, (cx, cy + r // 2), 2)


def _icon_camera(driver: DisplayDriver, cx: int, cy: int, r: int, color) -> None:
    body = pygame.Rect(cx - r, cy - r // 2, r * 2, r)
    driver.rect(color, body, 2)
    driver.circle(color, (cx, cy), max(2, r // 3), 2)
    driver.rect(color, pygame.Rect(cx - r // 3, cy - r // 2 - 4, r // 2, 4), 2)


def _icon_gear(driver: DisplayDriver, cx: int, cy: int, r: int, color) -> None:
    driver.circle(color, (cx, cy), r // 2, 2)
    for i in range(8):
        ang = math.radians(i * 45)
        x1, y1 = cx + math.cos(ang) * (r - 3), cy + math.sin(ang) * (r - 3)
        x2, y2 = cx + math.cos(ang) * r, cy + math.sin(ang) * r
        driver.line(color, (int(x1), int(y1)), (int(x2), int(y2)), 2)


def _icon_gamepad(driver: DisplayDriver, cx: int, cy: int, r: int, color) -> None:
    body = pygame.Rect(cx - r, cy - r // 2, r * 2, r)
    driver.rect(color, body, 2)
    lx = cx - r // 2
    driver.line(color, (lx - 3, cy), (lx + 3, cy), 2)
    driver.line(color, (lx, cy - 3), (lx, cy + 3), 2)
    rx = cx + r // 2
    driver.circle(color, (rx - 3, cy - 2), 2)
    driver.circle(color, (rx + 3, cy + 2), 2)


def _icon_wifi(driver: DisplayDriver, cx: int, cy: int, r: int, color) -> None:
    for i, radius in enumerate((r, int(r * 0.66), int(r * 0.33))):
        rect = pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2)
        driver.arc(color, rect, math.radians(210), math.radians(330), 2)
    driver.circle(color, (cx, cy + 1), 2)


def _icon_check(driver: DisplayDriver, cx: int, cy: int, r: int, color) -> None:
    driver.line(color, (cx - r, cy), (cx - r // 4, cy + r // 2), 3)
    driver.line(color, (cx - r // 4, cy + r // 2), (cx + r, cy - r // 2), 3)


class DashboardApp:
    """Smart Home Command Center dashboard, rendered via ``DisplayDriver``."""

    BG = (0x12, 0x12, 0x12)
    CARD_BG = (0x1E, 0x1E, 0x1E)
    ACCENT_GREEN = (0x00, 0xE6, 0x76)
    ACCENT_BLUE = (0x00, 0xB0, 0xFF)
    ALERT_RED = (0xFF, 0x52, 0x52)
    ACCENT_YELLOW = (255, 214, 0)
    TEXT = (0xFF, 0xFF, 0xFF)
    MUTED = (150, 150, 150)

    STATUS_BAR_H = 30
    DOTS_H = 14
    AUTO_ROTATE_SECONDS = 12.0
    MANUAL_PAUSE_SECONDS = 20.0
    NEWS_PAGE_ROTATE_SECONDS = 15.0
    ICON_FLASH_SECONDS = 0.18

    # aireminder MCP HTTP server (mcp/python/mcp_server_lite.py), running
    # locally as the aireminder-mcp.service systemd unit.
    REMINDER_API_URL = "http://127.0.0.1:8000/api/tools/call"
    REMINDER_POLL_SECONDS = 30.0
    REMINDER_TIMEOUT_SECONDS = 2.0
    BLINK_HZ = 2.0

    # Live news pulled from public RSS feeds: (category label, feed URL, max
    # headlines to take from that feed).
    NEWS_SOURCES = [
        ("Football", "http://feeds.bbci.co.uk/sport/football/rss.xml", 3),
        ("AI", "https://techcrunch.com/category/artificial-intelligence/feed/", 3),
        ("Singapore", "https://www.straitstimes.com/news/singapore/rss.xml", 3),
    ]
    NEWS_POLL_SECONDS = 900.0
    NEWS_FETCH_TIMEOUT_SECONDS = 5.0

    # Text size options selectable from the Settings screen: (label, font
    # scale multiplier applied to every base font size).
    FONT_SIZE_OPTIONS = [("Small", 0.85), ("Normal", 1.0), ("Large", 1.15), ("X-Large", 1.3)]
    DEFAULT_FONT_SIZE_INDEX = 1

    QUICK_ACTIONS = ["lights", "ac", "security", "cameras", "games", "settings"]
    QUICK_LABELS = ["Lights", "AC", "Security", "Cameras", "Games", "Settings"]
    QUICK_ICONS = [_icon_bulb, _icon_snowflake, _icon_lock, _icon_camera, _icon_gamepad, _icon_gear]

    def __init__(self, driver: DisplayDriver, runtime_dir: str, rotate_180: bool = True) -> None:
        self.driver = driver
        self.width = driver.width
        self.height = driver.height
        self.rotate_180 = rotate_180

        self.data_file = os.path.join(runtime_dir, "dashboard_data.json")
        self.action_file = os.path.join(runtime_dir, "dashboard_action.json")
        self.voice_state_file = os.path.join(runtime_dir, "digitalface_voice_state")
        self.settings_file = os.path.join(runtime_dir, "dashboard_settings.json")

        self.data: dict = copy.deepcopy(DEMO_DATA)
        self._next_data_poll_at = 0.0

        self._live_reminder: dict | None = None
        self._live_reminders: list[dict] | None = None
        self._next_reminder_poll_at = 0.0
        self._reminder_alerted_ids: set[str] = set()

        self._live_news: list[str] | None = None
        self._next_news_poll_at = 0.0

        self.auto_rotate_enabled = True
        self.font_size_index = self.DEFAULT_FONT_SIZE_INDEX
        self._load_settings()
        self.settings_open = False

        self.page = PAGE_HOME
        self._next_rotate_at = time.time() + self.AUTO_ROTATE_SECONDS
        self._manual_pause_until = 0.0

        self._news_page_index = 0
        self._next_news_page_rotate_at = time.time() + self.NEWS_PAGE_ROTATE_SECONDS
        self._news_manual_pause_until = 0.0

        self.voice_state = "idle"
        self.voice_response_text = ""
        self._next_voice_poll_at = 0.0
        self._voice_local_override_until = 0.0
        self._voice_demo_started_at = 0.0

        self._icon_flash: dict[int, float] = {}

        self._build_fonts()

    # ── public contract: update() mutates state, render() only draws ──────

    def update(self, now: float) -> None:
        self._load_data(now)
        self._poll_reminder(now)
        if self._live_reminder is not None:
            self.data["reminder"] = self._live_reminder
        if self._live_reminders is not None:
            self.data["reminders"] = self._live_reminders
        self._maybe_alert_active_reminders(now)

        self._poll_news(now)
        if self._live_news is not None:
            self.data["news"] = self._live_news

        if self._voice_local_override_until > now:
            elapsed = now - self._voice_demo_started_at
            if elapsed < 1.4:
                self.voice_state = "listening"
            elif elapsed < 2.6:
                self.voice_state = "processing"
            else:
                self.voice_state = "response"
        else:
            self._poll_voice_state(now)

        if now >= self._next_news_page_rotate_at and now >= self._news_manual_pause_until:
            news = self.data.get("news") or []
            if news:
                self._news_page_index = (self._news_page_index + 1) % len(news)
            self._next_news_page_rotate_at = now + self.NEWS_PAGE_ROTATE_SECONDS

        if (
            not self.settings_open
            and self.auto_rotate_enabled
            and now >= self._next_rotate_at
            and now >= self._manual_pause_until
        ):
            self.page = (self.page + 1) % PAGE_COUNT
            self._next_rotate_at = now + self.AUTO_ROTATE_SECONDS

        for idx in [i for i, until in self._icon_flash.items() if until < now]:
            del self._icon_flash[idx]

    def render(self, now: float) -> None:
        d = self.driver
        d.fill(self.BG)
        self._draw_status_bar(now)
        if self.settings_open:
            self._draw_settings_page(now)
            return
        if self.page == PAGE_HOME:
            self._draw_home_page(now)
        elif self.page == PAGE_REMINDER:
            self._draw_reminder_page(now)
        elif self.page == PAGE_NEWS:
            self._draw_news_page(now)
        elif self.page == PAGE_WEATHER:
            self._draw_weather_page(now)
        elif self.page == PAGE_ENERGY:
            self._draw_energy_page(now)
        else:
            self._draw_security_page(now)
        self._draw_page_dots()

    def handle_touch_tap(self, sx: int, sy: int, now: float) -> str | None:
        """Handle a tap at screen coords (sx, sy). Returns "games" to open
        the game selection menu, else None."""
        if self.settings_open:
            return self._handle_settings_tap(sx, sy, now)

        if self.page == PAGE_HOME:
            quick_row = self._quick_row_rect()
            if quick_row.collidepoint(sx, sy):
                idx = min(len(self.QUICK_ACTIONS) - 1, max(0, (sx * len(self.QUICK_ACTIONS)) // self.width))
                self._icon_flash[idx] = now + self.ICON_FLASH_SECONDS
                action = self.QUICK_ACTIONS[idx]
                if action == "settings":
                    self.settings_open = True
                    return None
                if action == "games":
                    return "games"
                self._trigger_action(action, now)
                return None

            voice_rect = self._voice_rect()
            if voice_rect.collidepoint(sx, sy):
                self._cycle_voice_demo(now)
                return None

        if self.page == PAGE_NEWS:
            news = self.data.get("news") or []
            if news:
                if self._news_button_rect(False).collidepoint(sx, sy):
                    self._news_page_index = (self._news_page_index - 1) % len(news)
                    self._news_manual_pause_until = now + self.MANUAL_PAUSE_SECONDS
                    self._next_news_page_rotate_at = now + self.NEWS_PAGE_ROTATE_SECONDS
                    return None
                if self._news_button_rect(True).collidepoint(sx, sy):
                    self._news_page_index = (self._news_page_index + 1) % len(news)
                    self._news_manual_pause_until = now + self.MANUAL_PAUSE_SECONDS
                    self._next_news_page_rotate_at = now + self.NEWS_PAGE_ROTATE_SECONDS
                    return None

        # Anywhere else in the content area: navigate pages left/right.
        self._manual_pause_until = now + self.MANUAL_PAUSE_SECONDS
        self._next_rotate_at = now + self.AUTO_ROTATE_SECONDS
        if sx < self.width // 2:
            self.page = (self.page - 1) % PAGE_COUNT
        else:
            self.page = (self.page + 1) % PAGE_COUNT
        return None

    def _handle_settings_tap(self, sx: int, sy: int, now: float) -> None:
        if self._settings_toggle_rect().collidepoint(sx, sy):
            self.auto_rotate_enabled = not self.auto_rotate_enabled
            self._save_settings()
            if self.auto_rotate_enabled:
                self._next_rotate_at = now + self.AUTO_ROTATE_SECONDS
            return None
        if self._settings_font_rect().collidepoint(sx, sy):
            self.font_size_index = (self.font_size_index + 1) % len(self.FONT_SIZE_OPTIONS)
            self._build_fonts()
            self._save_settings()
            return None
        if self._settings_back_rect().collidepoint(sx, sy):
            self.settings_open = False
            return None
        return None

    # ── data / voice polling ───────────────────────────────────────────────

    def _load_data(self, now: float) -> None:
        if now < self._next_data_poll_at:
            return
        self._next_data_poll_at = now + 2.0
        merged = copy.deepcopy(DEMO_DATA)
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                _deep_update(merged, loaded)
        except (OSError, ValueError):
            pass
        self.data = merged

    def _poll_reminder(self, now: float) -> None:
        """Refresh the reminder card/page from the aireminder MCP server's
        get_today_reminders tool. Keeps the last successfully fetched
        reminders on failure/timeout so a momentary outage doesn't blank the
        card."""
        if now < self._next_reminder_poll_at:
            return
        self._next_reminder_poll_at = now + self.REMINDER_POLL_SECONDS
        reminders = self._fetch_today_reminders()
        if reminders is not None:
            self._live_reminders = reminders
            self._live_reminder = reminders[0] if reminders else {
                "id": "", "title": "No reminders today", "time": "", "urgent": False, "active": False,
            }

    def _fetch_today_reminders(self) -> list[dict] | None:
        payload = json.dumps({"name": "get_today_reminders", "arguments": {}}).encode("utf-8")
        req = urllib.request.Request(
            self.REMINDER_API_URL,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.REMINDER_TIMEOUT_SECONDS) as resp:
                body = json.load(resp)
        except (OSError, ValueError):
            return None
        if not isinstance(body, dict) or not body.get("success"):
            return None

        items = [item for item in (body.get("data") or []) if not item.get("isCompleted")]
        return [self._reminder_from_item(item) for item in items]

    @staticmethod
    def _reminder_from_item(item: dict) -> dict:
        title = str(item.get("title") or "Reminder")
        if len(title) > 46:
            title = title[:45] + "\u2026"

        due_str = str(item.get("dueDateTime") or item.get("dueDate") or "")
        time_str = due_str
        minutes_until = None
        for fmt, time_fmt in (("%b %d, %Y %I:%M %p", "%I:%M %p"), ("%b %d, %Y", "%b %d")):
            try:
                due_dt = datetime.strptime(due_str, fmt)
            except ValueError:
                continue
            time_str = due_dt.strftime(time_fmt).lstrip("0")
            minutes_until = (due_dt - datetime.now()).total_seconds() / 60.0
            break

        # "urgent" = starting soon (within 15 min). "active" = the event is
        # currently "on" (within its default 30-minute window after the due
        # time) -- this is what blinks and triggers the sound alert. Stale
        # aireminder "overdue" statuses (e.g. mis-tagged recurring items) are
        # intentionally ignored here; only the actual due time matters.
        urgent = minutes_until is not None and 0 <= minutes_until <= 15
        active = minutes_until is not None and -EVENT_ACTIVE_WINDOW_MINUTES <= minutes_until <= 0
        return {
            "id": str(item.get("id") or ""),
            "title": title,
            "time": time_str,
            "urgent": urgent,
            "active": active,
        }

    def _maybe_alert_active_reminders(self, now: float) -> None:
        """Play a spoken sound alert the moment a reminder becomes "active"
        (on). Only fires once per reminder occurrence."""
        reminders = self.data.get("reminders") or []
        active_ids = set()
        for reminder in reminders:
            rid = reminder.get("id")
            if not rid or not reminder.get("active"):
                continue
            active_ids.add(rid)
            if rid not in self._reminder_alerted_ids:
                self._reminder_alerted_ids.add(rid)
                self._play_reminder_sound(str(reminder.get("title") or "Reminder"))
        # Drop ids that are no longer active so a future occurrence can re-alert.
        self._reminder_alerted_ids &= active_ids

    @staticmethod
    def _play_reminder_sound(title: str) -> None:
        try:
            subprocess.Popen(
                ["speak", f"Reminder: {title}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass

    def _poll_news(self, now: float) -> None:
        if now < self._next_news_poll_at:
            return
        self._next_news_poll_at = now + self.NEWS_POLL_SECONDS
        news = self._fetch_live_news()
        if news:
            self._live_news = news

    def _fetch_live_news(self) -> list[dict] | None:
        items: list[dict] = []
        any_ok = False
        for category, url, limit in self.NEWS_SOURCES:
            entries = self._fetch_rss_entries(url, limit)
            if entries is None:
                continue
            any_ok = True
            for title, summary in entries:
                items.append({"category": category, "title": title, "summary": summary})
        return items if any_ok else None

    @classmethod
    def _fetch_rss_entries(cls, url: str, limit: int) -> list[tuple[str, str]] | None:
        req = urllib.request.Request(url, headers={"User-Agent": "digitalface-dashboard/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=cls.NEWS_FETCH_TIMEOUT_SECONDS) as resp:
                body = resp.read()
        except OSError:
            return None
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            return None

        entries: list[tuple[str, str]] = []
        for item in root.findall(".//item")[:limit]:
            title_el = item.find("title")
            title = (title_el.text or "").strip() if title_el is not None else ""
            if not title:
                continue
            if len(title) > 90:
                title = title[:89] + "\u2026"

            desc_el = item.find("description")
            summary = cls._strip_html((desc_el.text or "").strip()) if desc_el is not None else ""
            if len(summary) > 220:
                summary = summary[:219] + "\u2026"
            entries.append((title, summary))
        return entries

    @staticmethod
    def _strip_html(text: str) -> str:
        return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()

    def _poll_voice_state(self, now: float) -> None:
        if now < self._next_voice_poll_at:
            return
        self._next_voice_poll_at = now + 0.3
        state = "idle"
        response_text = ""
        try:
            with open(self.voice_state_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                if ":" in content:
                    state, _, response_text = content.partition(":")
                else:
                    state = content
                state = state.strip().lower()
        except OSError:
            pass
        if state not in ("idle", "listening", "processing", "response", "error"):
            state = "idle"
        self.voice_state = state
        self.voice_response_text = response_text.strip()

    def _cycle_voice_demo(self, now: float) -> None:
        self._voice_local_override_until = now + 4.2
        self._voice_demo_started_at = now
        self.voice_response_text = "Living Room Lights Turned On"

    def _trigger_action(self, action: str, now: float) -> None:
        try:
            os.makedirs(os.path.dirname(self.action_file), exist_ok=True)
            tmp_path = f"{self.action_file}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump({"action": action, "ts": now}, f)
            os.replace(tmp_path, self.action_file)
        except OSError:
            pass

    def _load_settings(self) -> None:
        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(loaded, dict):
            return
        if "auto_rotate_enabled" in loaded:
            self.auto_rotate_enabled = bool(loaded["auto_rotate_enabled"])
        if "font_size_index" in loaded:
            try:
                idx = int(loaded["font_size_index"])
            except (TypeError, ValueError):
                idx = self.font_size_index
            if 0 <= idx < len(self.FONT_SIZE_OPTIONS):
                self.font_size_index = idx

    def _save_settings(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
            tmp_path = f"{self.settings_file}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump({
                    "auto_rotate_enabled": self.auto_rotate_enabled,
                    "font_size_index": self.font_size_index,
                }, f)
            os.replace(tmp_path, self.settings_file)
        except OSError:
            pass

    def _build_fonts(self) -> None:
        scale = self.FONT_SIZE_OPTIONS[self.font_size_index][1]
        self.font_time = pygame.font.Font(None, round(30 * scale))
        self.font_status = pygame.font.Font(None, round(22 * scale))
        self.font_card_title = pygame.font.Font(None, round(20 * scale))
        self.font_card_body = pygame.font.Font(None, round(24 * scale))
        self.font_big = pygame.font.Font(None, round(64 * scale))
        self.font_label = pygame.font.Font(None, round(18 * scale))
        self.font_section = pygame.font.Font(None, round(26 * scale))

    # ── layout rects ────────────────────────────────────────────────────────

    def _content_top(self) -> int:
        return self.STATUS_BAR_H

    def _content_bottom(self) -> int:
        return self.height - self.DOTS_H

    def _quick_row_rect(self) -> pygame.Rect:
        h = 52
        return pygame.Rect(0, self._content_bottom() - h, self.width, h)

    def _voice_rect(self) -> pygame.Rect:
        quick = self._quick_row_rect()
        h = 66
        return pygame.Rect(8, quick.top - h - 4, self.width - 16, h)

    def _settings_toggle_rect(self) -> pygame.Rect:
        w, h = 54, 28
        return pygame.Rect(self.width - 16 - w, self._content_top() + 40, w, h)

    def _settings_back_rect(self) -> pygame.Rect:
        w, h = 120, 36
        return pygame.Rect(16, self.height - h - 16, w, h)

    def _settings_font_rect(self) -> pygame.Rect:
        w, h = 100, 28
        return pygame.Rect(self.width - 16 - w, self._content_top() + 108, w, h)

    def _news_button_rect(self, right: bool) -> pygame.Rect:
        w, h = 110, 34
        y = self._content_bottom() - h - 6
        x = self.width - 16 - w if right else 16
        return pygame.Rect(x, y, w, h)

    # ── drawing: chrome ─────────────────────────────────────────────────────

    def _draw_status_bar(self, now: float) -> None:
        d = self.driver
        d.rect(self.CARD_BG, pygame.Rect(0, 0, self.width, self.STATUS_BAR_H))
        d.line((40, 40, 40), (0, self.STATUS_BAR_H - 1), (self.width, self.STATUS_BAR_H - 1))

        time_str = time.strftime("%I:%M %p")
        d.text(time_str, self.TEXT, (10, 5), font=self.font_time)

        status = self.data.get("status", {})
        wifi_ok = bool(status.get("wifi", True))
        mqtt_ok = bool(status.get("mqtt", True))
        temp_c = status.get("indoor_temp_c")
        temp_str = f"{temp_c}\u00b0C" if temp_c is not None else "--\u00b0C"

        x = self.width - 10
        for label, ok in (("MQTT", mqtt_ok), ("WiFi", wifi_ok)):
            color = self.ACCENT_GREEN if ok else self.ALERT_RED
            w, h = self.font_status.size(label)
            x -= w
            d.text(label, color, (x, (self.STATUS_BAR_H - h) // 2), font=self.font_status)
            x -= 10
            d.circle(color, (x - 4, self.STATUS_BAR_H // 2), 4)
            x -= 14

        w, h = self.font_status.size(temp_str)
        x -= w
        d.text(temp_str, self.TEXT, (x, (self.STATUS_BAR_H - h) // 2), font=self.font_status)

    def _draw_page_dots(self) -> None:
        d = self.driver
        y = self.height - self.DOTS_H // 2 - 1
        spacing = 14
        x0 = (self.width - (PAGE_COUNT - 1) * spacing) // 2
        for i in range(PAGE_COUNT):
            cx = x0 + i * spacing
            color = self.ACCENT_BLUE if i == self.page else (70, 70, 70)
            d.circle(color, (cx, y), 3)

    def _card(self, rect: pygame.Rect, accent) -> None:
        d = self.driver
        d.rect(self.CARD_BG, rect, 0)
        d.rect(accent, pygame.Rect(rect.left, rect.top, 4, rect.height), 0)

    def _blink_visible(self, now: float) -> bool:
        """Returns an alternating True/False at BLINK_HZ, used to make
        "active" (on) reminders blink."""
        return int(now * self.BLINK_HZ * 2) % 2 == 0

    # ── drawing: home page ──────────────────────────────────────────────────

    def _draw_home_page(self, now: float) -> None:
        d = self.driver
        top = self._content_top()
        pad = 6

        reminder = self.data.get("reminder", {})
        active = bool(reminder.get("active", False))
        urgent = bool(reminder.get("urgent", False))
        if active:
            accent = self.ALERT_RED if self._blink_visible(now) else self.ACCENT_YELLOW
        elif urgent:
            accent = self.ALERT_RED
        else:
            accent = self.ACCENT_GREEN
        reminder_rect = pygame.Rect(8, top + pad, self.width - 16, 46)
        self._card(reminder_rect, accent)
        _icon_bell(d, reminder_rect.left + 26, reminder_rect.centery, 9, accent)
        if active:
            label = "Happening Now"
        elif urgent:
            label = "Upcoming (< 15 min)"
        else:
            label = "Next Reminder"
        d.text(label, self.MUTED, (reminder_rect.left + 46, reminder_rect.top + 5), font=self.font_card_title)
        title = reminder.get("title", "No reminders")
        rtime = reminder.get("time", "")
        line = f"{title}  \u00b7  {rtime}" if rtime else title
        d.text(line, self.TEXT, (reminder_rect.left + 46, reminder_rect.top + 22), font=self.font_card_body)

        news_rect = pygame.Rect(8, reminder_rect.bottom + pad, self.width - 16, 46)
        self._card(news_rect, self.ACCENT_BLUE)
        _icon_newspaper(d, news_rect.left + 26, news_rect.centery, 9, self.ACCENT_BLUE)
        d.text("Latest News", self.MUTED, (news_rect.left + 46, news_rect.top + 5), font=self.font_card_title)
        news = self.data.get("news") or []
        if news:
            item = news[self._news_page_index % len(news)]
            headline = f"{item.get('category', 'News')}: {item.get('title', '')}"
        else:
            headline = "No news available"
        if len(headline) > 42:
            headline = headline[:41] + "\u2026"
        d.text(headline, self.TEXT, (news_rect.left + 46, news_rect.top + 22), font=self.font_card_body)

        voice_rect = self._voice_rect()
        self._draw_voice_panel(voice_rect, now)

        self._draw_quick_controls(self._quick_row_rect(), now)

    def _draw_voice_panel(self, rect: pygame.Rect, now: float) -> None:
        d = self.driver
        colors = {
            "idle": self.ACCENT_GREEN,
            "listening": self.ACCENT_YELLOW,
            "processing": self.ACCENT_BLUE,
            "response": self.ACCENT_GREEN,
            "error": self.ALERT_RED,
        }
        color = colors.get(self.voice_state, self.ACCENT_GREEN)
        d.rect(self.CARD_BG, rect, 0)
        d.rect(color, rect, 2)

        mic_cx = rect.left + 40
        mic_cy = rect.centery

        if self.voice_state in ("listening", "processing"):
            pulse = (math.sin(now * 6.0) + 1.0) * 0.5
            ring_r = int(16 + pulse * 4)
            d.circle(color, (mic_cx, mic_cy), ring_r, 2)

        if self.voice_state == "response":
            _icon_check(d, mic_cx, mic_cy, 10, color)
        else:
            _icon_mic(d, mic_cx, mic_cy, 8, color)

        messages = {
            "idle": ("Ready", "Tap or say \"Hey Home\""),
            "listening": ("Listening...", ""),
            "processing": ("Processing...", ""),
            "response": (self.voice_response_text or "Done", ""),
            "error": ("Error", "Please try again"),
        }
        title, subtitle = messages.get(self.voice_state, ("Ready", ""))
        d.text(title, self.TEXT, (rect.left + 74, rect.top + 14), font=self.font_section)
        if subtitle:
            d.text(subtitle, self.MUTED, (rect.left + 74, rect.top + 38), font=self.font_card_title)

    def _draw_quick_controls(self, rect: pygame.Rect, now: float) -> None:
        d = self.driver
        col_w = rect.width // len(self.QUICK_ACTIONS)
        for i, (action, label, icon_fn) in enumerate(zip(self.QUICK_ACTIONS, self.QUICK_LABELS, self.QUICK_ICONS)):
            col = pygame.Rect(rect.left + i * col_w, rect.top, col_w, rect.height)
            flashed = self._icon_flash.get(i, 0.0) > now
            if flashed:
                d.rect((40, 40, 40), col, 0)
            cx, cy = col.centerx, col.top + 18
            icon_fn(d, cx, cy, 11, self.ACCENT_BLUE if not flashed else self.TEXT)
            w, h = self.font_label.size(label)
            d.text(label, self.TEXT if flashed else self.MUTED, (cx - w // 2, col.top + 36), font=self.font_label)

    # ── drawing: reminder page ──────────────────────────────────────────────

    def _draw_reminder_page(self, now: float) -> None:
        d = self.driver
        top = self._content_top()
        d.text("Reminders Today", self.MUTED, (16, top + 8), font=self.font_card_title)

        reminders = self.data.get("reminders") or []
        if not reminders:
            d.text("No reminders today", self.TEXT, (16, top + 40), font=self.font_card_body)
            return

        y = top + 32
        row_h = 46
        max_rows = (self._content_bottom() - y) // row_h
        for reminder in reminders[:max_rows]:
            active = bool(reminder.get("active", False))
            urgent = bool(reminder.get("urgent", False))
            if active:
                accent = self.ALERT_RED if self._blink_visible(now) else self.ACCENT_YELLOW
            elif urgent:
                accent = self.ALERT_RED
            else:
                accent = self.ACCENT_GREEN
            row_rect = pygame.Rect(8, y, self.width - 16, row_h - 6)
            self._card(row_rect, accent)
            _icon_bell(d, row_rect.left + 22, row_rect.centery, 8, accent)

            title = str(reminder.get("title") or "Reminder")
            rtime = str(reminder.get("time") or "")
            status_label = "Happening Now" if active else ("Due soon" if urgent else "")
            header = f"{rtime}  \u00b7  {status_label}" if status_label else rtime
            if header:
                d.text(header, self.MUTED, (row_rect.left + 38, row_rect.top + 4), font=self.font_label)
            if len(title) > 44:
                title = title[:43] + "\u2026"
            d.text(title, self.TEXT, (row_rect.left + 38, row_rect.top + 19), font=self.font_card_body)

            y += row_h

    # ── drawing: news page ───────────────────────────────────────────────────

    def _draw_news_page(self, now: float) -> None:
        d = self.driver
        top = self._content_top()

        news = self.data.get("news") or []
        if not news:
            d.text("Latest News", self.MUTED, (16, top + 8), font=self.font_card_title)
            d.text("No news available", self.TEXT, (16, top + 40), font=self.font_card_body)
            return

        idx = self._news_page_index % len(news)
        item = news[idx]
        category = str(item.get("category", "News"))
        title = str(item.get("title", ""))
        summary = str(item.get("summary", ""))

        d.text(category, self.ACCENT_BLUE, (16, top + 8), font=self.font_card_title)
        counter = f"{idx + 1} / {len(news)}"
        w, _ = self.font_card_title.size(counter)
        d.text(counter, self.MUTED, (self.width - 16 - w, top + 8), font=self.font_card_title)

        content_width = self.width - 32
        buttons_top = self._news_button_rect(False).top
        y = top + 32
        for line in self._wrap_text(title, self.font_section, content_width)[:3]:
            if y + 24 > buttons_top:
                break
            d.text(line, self.TEXT, (16, y), font=self.font_section)
            y += 24

        y += 8
        for line in self._wrap_text(summary, self.font_card_body, content_width):
            if y + 20 > buttons_top:
                break
            d.text(line, self.MUTED, (16, y), font=self.font_card_body)
            y += 20

        for rect, label in ((self._news_button_rect(False), "< Prev"), (self._news_button_rect(True), "Next >")):
            d.rect(self.CARD_BG, rect, 0)
            d.rect(self.ACCENT_BLUE, rect, 2)
            w, h = self.font_card_body.size(label)
            d.text(label, self.TEXT, (rect.centerx - w // 2, rect.centery - h // 2), font=self.font_card_body)

    @staticmethod
    def _wrap_text(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    # ── drawing: weather page ───────────────────────────────────────────────

    def _draw_weather_page(self, now: float) -> None:
        d = self.driver
        top = self._content_top()
        weather = self.data.get("weather", {})
        cx = self.width // 2

        d.text("Weather", self.MUTED, (16, top + 10), font=self.font_card_title)

        temp_c = weather.get("temp_c")
        temp_str = f"{temp_c}\u00b0C" if temp_c is not None else "--\u00b0C"
        w, _ = self.font_big.size(temp_str)
        d.text(temp_str, self.TEXT, (cx - w // 2, top + 34), font=self.font_big)

        condition = str(weather.get("condition", "Unknown"))
        w, _ = self.font_section.size(condition)
        d.text(condition, self.ACCENT_BLUE, (cx - w // 2, top + 104), font=self.font_section)

        humidity = weather.get("humidity")
        hum_str = f"Humidity: {humidity}%" if humidity is not None else "Humidity: --"
        w, _ = self.font_card_body.size(hum_str)
        d.text(hum_str, self.TEXT, (cx - w // 2, top + 140), font=self.font_card_body)

        forecast = str(weather.get("forecast", ""))
        if forecast:
            w, _ = self.font_card_body.size(forecast)
            d.text(forecast, self.MUTED, (cx - w // 2, top + 168), font=self.font_card_body)

    # ── drawing: energy page ────────────────────────────────────────────────

    def _draw_gauge_row(self, y: int, label: str, value_str: str, fraction: float, color) -> None:
        d = self.driver
        d.text(label, self.MUTED, (16, y), font=self.font_card_title)
        w, _ = self.font_card_body.size(value_str)
        d.text(value_str, self.TEXT, (self.width - 16 - w, y), font=self.font_card_body)
        bar_rect = pygame.Rect(16, y + 24, self.width - 32, 12)
        d.rect((40, 40, 40), bar_rect, 0)
        fill_w = int(bar_rect.width * max(0.0, min(1.0, fraction)))
        if fill_w > 0:
            d.rect(color, pygame.Rect(bar_rect.left, bar_rect.top, fill_w, bar_rect.height), 0)

    def _draw_energy_page(self, now: float) -> None:
        top = self._content_top()
        energy = self.data.get("energy", {})
        d = self.driver
        d.text("Energy", self.MUTED, (16, top + 10), font=self.font_card_title)

        usage_kw = float(energy.get("usage_kw") or 0.0)
        solar_kw = float(energy.get("solar_kw") or 0.0)
        battery_pct = float(energy.get("battery_pct") or 0.0)

        self._draw_gauge_row(top + 38, "Usage", f"{usage_kw:.1f} kW", usage_kw / 5.0, self.ACCENT_BLUE)
        self._draw_gauge_row(top + 100, "Solar Output", f"{solar_kw:.1f} kW", solar_kw / 5.0, self.ACCENT_GREEN)
        self._draw_gauge_row(top + 162, "Battery", f"{battery_pct:.0f}%", battery_pct / 100.0, self.ACCENT_YELLOW)

    # ── drawing: security page ──────────────────────────────────────────────

    def _draw_security_page(self, now: float) -> None:
        d = self.driver
        top = self._content_top()
        security = self.data.get("security", {})
        d.text("Security", self.MUTED, (16, top + 6), font=self.font_card_title)

        y = top + 28
        _icon_lock(d, 26, y + 6, 8, self.ACCENT_GREEN)
        d.text("Doors", self.TEXT, (42, y), font=self.font_card_body)
        y += 22
        for name, state in (security.get("door_sensors") or {}).items():
            ok = str(state).lower() in ("closed", "ok", "locked")
            color = self.ACCENT_GREEN if ok else self.ALERT_RED
            d.circle(color, (24, y + 7), 4)
            d.text(f"{name}: {state}", self.TEXT, (36, y), font=self.font_label)
            y += 18

        y += 6
        _icon_lock(d, 26, y + 6, 8, self.ACCENT_BLUE)
        d.text("Windows", self.TEXT, (42, y), font=self.font_card_body)
        y += 22
        for name, state in (security.get("window_sensors") or {}).items():
            ok = str(state).lower() in ("closed", "ok", "locked")
            color = self.ACCENT_GREEN if ok else self.ALERT_RED
            d.circle(color, (24, y + 7), 4)
            d.text(f"{name}: {state}", self.TEXT, (36, y), font=self.font_label)
            y += 18

        cam_status = str(security.get("cameras", "Unknown"))
        cam_ok = cam_status.lower() in ("ok", "online", "active")
        cam_color = self.ACCENT_GREEN if cam_ok else self.ALERT_RED
        _icon_camera(d, 26, y + 8, 9, cam_color)
        d.text(f"Cameras: {cam_status}", self.TEXT, (42, y), font=self.font_label)

    # ── drawing: settings page ──────────────────────────────────────────────

    def _draw_toggle_switch(self, rect: pygame.Rect, on: bool) -> None:
        d = self.driver
        track_color = self.ACCENT_GREEN if on else (70, 70, 70)
        d.rect(track_color, rect, 0)
        knob_r = rect.height // 2 - 2
        knob_cx = rect.right - knob_r - 3 if on else rect.left + knob_r + 3
        d.circle(self.TEXT, (knob_cx, rect.centery), knob_r)

    def _draw_settings_page(self, now: float) -> None:
        d = self.driver
        top = self._content_top()
        d.text("Settings", self.MUTED, (16, top + 8), font=self.font_card_title)

        row_rect = pygame.Rect(8, top + 32, self.width - 16, 60)
        self._card(row_rect, self.ACCENT_BLUE)
        d.text("Auto-Rotate Pages", self.TEXT, (row_rect.left + 16, row_rect.top + 10), font=self.font_card_body)
        subtitle = "Pages advance automatically" if self.auto_rotate_enabled else "Pages stay until you swipe"
        d.text(subtitle, self.MUTED, (row_rect.left + 16, row_rect.top + 32), font=self.font_label)
        toggle_rect = self._settings_toggle_rect()
        self._draw_toggle_switch(toggle_rect, self.auto_rotate_enabled)

        font_row_rect = pygame.Rect(8, row_rect.bottom + 8, self.width - 16, 60)
        self._card(font_row_rect, self.ACCENT_BLUE)
        d.text("Text Size", self.TEXT, (font_row_rect.left + 16, font_row_rect.top + 10), font=self.font_card_body)
        d.text("Tap to cycle", self.MUTED, (font_row_rect.left + 16, font_row_rect.top + 32), font=self.font_label)
        font_rect = self._settings_font_rect()
        d.rect((40, 40, 40), font_rect, 0)
        d.rect(self.ACCENT_GREEN, font_rect, 2)
        font_label = self.FONT_SIZE_OPTIONS[self.font_size_index][0]
        w, h = self.font_label.size(font_label)
        d.text(font_label, self.TEXT, (font_rect.centerx - w // 2, font_rect.centery - h // 2), font=self.font_label)

        back_rect = self._settings_back_rect()
        d.rect(self.CARD_BG, back_rect, 0)
        d.rect(self.ACCENT_BLUE, back_rect, 2)
        label = "Back"
        w, h = self.font_card_body.size(label)
        d.text(label, self.TEXT, (back_rect.centerx - w // 2, back_rect.centery - h // 2), font=self.font_card_body)

