#!/usr/bin/env python3
"""
Picoclaw process hook — displays incoming user messages on the digitalface LCD.

Picoclaw starts this script as a subprocess and communicates via newline-delimited
JSON-RPC on stdin/stdout.  The script observes "turn_start" events and forwards
the user message text to the digitalface HMI display for 60 seconds (default),
dismissing any currently shown message first.

Configuration (environment variables):
  DIGITALFACE_HMI_SOCKET  Path to the digitalface Unix datagram socket
                          (default: ~/projects/digitalface/.runtime/digitalface_hmi.sock)
  DIGITALFACE_HMI_FILE    File-based fallback path (optional)
  DIGITALFACE_HMI_DURATION Display duration in seconds (default: 60)
"""

import json
import os
import socket
import sys
import time

_LOG_FILE = os.path.expanduser("~/projects/digitalface/.runtime/hook_debug.log")

def _log(msg: str) -> None:
    try:
        with open(_LOG_FILE, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except OSError:
        pass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_SOCKET = os.path.expanduser(
    "~/projects/digitalface/.runtime/digitalface_hmi.sock"
)
HMI_SOCKET = os.environ.get("DIGITALFACE_HMI_SOCKET", _DEFAULT_SOCKET)
HMI_FILE = os.environ.get("DIGITALFACE_HMI_FILE", "")
DISPLAY_DURATION = float(os.environ.get("DIGITALFACE_HMI_DURATION", "60"))

# agent.EventKindTurnStart = 0 (first iota value in events.go)
EVENT_KIND_TURN_START = 0

SKIP_CHANNELS = {"", "system", "heartbeat"}

CHANNEL_PREFIX = {
    "telegram":  "[TG]",
    "discord":   "[DC]",
    "whatsapp":  "[WA]",
    "slack":     "[SL]",
}

# ---------------------------------------------------------------------------
# HMI helpers
# ---------------------------------------------------------------------------

def _send_hmi(payload: bytes) -> bool:
    """Send a raw JSON payload to the digitalface HMI (socket → file fallback)."""
    sock_path = HMI_SOCKET
    if sock_path and os.path.exists(sock_path):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            s.sendto(payload, sock_path)
            s.close()
            return True
        except OSError:
            pass
    if HMI_FILE:
        try:
            with open(HMI_FILE, "wb") as f:
                f.write(payload)
            return True
        except OSError:
            pass
    return False


def display_message(channel: str, text: str) -> None:
    """Dismiss the current overlay then show *text* for DISPLAY_DURATION seconds."""
    text = text.strip()
    if not text:
        return

    # Step 1: dismiss whatever is currently shown.
    ok1 = _send_hmi(json.dumps({"dismiss": True}).encode())
    _log(f"dismiss sent ok={ok1}")
    time.sleep(0.03)

    # Step 2: format and show the new message.
    prefix = CHANNEL_PREFIX.get(channel.lower(), "")
    display_text = f"{prefix} {text}".strip() if prefix else text
    ok2 = _send_hmi(json.dumps({"text": display_text, "duration": DISPLAY_DURATION}).encode())
    _log(f"show sent ok={ok2} text={display_text[:60]!r}")

# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------

def _reply(msg_id: int, result=None) -> None:
    """Write a JSON-RPC success response to stdout."""
    out = {"jsonrpc": "2.0", "id": msg_id, "result": result if result is not None else {}}
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue

        method = msg.get("method", "")
        msg_id = msg.get("id")

        if method == "hook.hello":
            # Mandatory handshake — picoclaw blocks until we respond.
            _reply(msg_id)

        elif method == "hook.event":
            params = msg.get("params") or {}
            kind = params.get("Kind")
            _log(f"hook.event kind={kind}")
            # Kind 0 == EventKindTurnStart (iota in events.go)
            if kind != EVENT_KIND_TURN_START:
                continue
            payload = params.get("Payload") or {}
            channel = payload.get("Channel", "")
            user_msg = payload.get("UserMessage", "")
            _log(f"turn_start channel={channel!r} msg={user_msg[:40]!r}")
            if channel not in SKIP_CHANNELS and user_msg:
                display_message(channel, user_msg)


if __name__ == "__main__":
    main()
