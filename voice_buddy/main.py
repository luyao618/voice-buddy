"""Entry point for Voice Buddy hook events."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from voice_buddy.config import load_user_config, get_repo_root
from voice_buddy.context import analyze_context
from voice_buddy.response import select_response
from voice_buddy.styles import load_style
from voice_buddy.tts import synthesize_to_file
from voice_buddy.player import play_audio

logger = logging.getLogger("voice_buddy")

_EVENT_NAME_MAP = {
    "SessionStart": "sessionstart",
    "SessionEnd": "sessionend",
    "Notification": "notification",
    "Stop": "stop",
}


def _debug(msg: str) -> None:
    """Legacy debug helper — routes to logger for backward compatibility."""
    logger.debug(msg)


def _get_assets_dir() -> Path:
    """Return the assets directory path."""
    return get_repo_root() / "assets"


def resolve_audio_path(style: str, audio_id: str) -> Optional[str]:
    """Look up a pre-packaged audio file. Returns path string or None."""
    assets_dir = _get_assets_dir()
    audio_file = assets_dir / "audio" / style / f"{audio_id}.mp3"
    if audio_file.exists():
        return str(audio_file)
    return None


def handle_hook_event(data: dict) -> None:
    """Process a hook event from Claude Code."""
    event_name = data.get("hook_event_name", "")
    event_key = _EVENT_NAME_MAP.get(event_name, "")

    # Load user config
    try:
        user_config = load_user_config()
    except Exception as e:
        logger.debug(f"Failed to load user config: {e}")
        return

    # Check global enable
    if not user_config.get("enabled", True):
        return

    # Check per-event enable
    if not user_config.get("events", {}).get(event_key, True):
        return

    style = user_config.get("style", "cute-girl")
    nickname = user_config.get("nickname", "Master")

    # Hotkey listener lifecycle wiring (macOS only; gated by config).
    if event_name == "SessionStart":
        try:
            from voice_buddy import listener_supervisor
            listener_supervisor.ensure_listener_for_session(
                str(data.get("session_id", "default"))
            )
        except Exception as e:
            logger.debug(f"hotkey supervisor (start) failed: {e}")
    elif event_name == "SessionEnd":
        try:
            from voice_buddy import listener_supervisor
            listener_supervisor.release_session(
                str(data.get("session_id", "default"))
            )
        except Exception as e:
            logger.debug(f"hotkey supervisor (end) failed: {e}")

    # Stop event goes through injector path
    if event_name == "Stop":
        handle_stop_event(data, user_config)
        return

    # Analyze context
    ctx = analyze_context(data)
    if ctx is None:
        return

    # Select response
    resp = select_response(ctx, style=style, nickname=nickname)
    if resp is None:
        return

    # Try pre-packaged audio first
    if resp.audio_id:
        audio_path = resolve_audio_path(style, resp.audio_id)
        if audio_path:
            play_audio(audio_path)
            return

    # Fallback to real-time TTS
    style_def = load_style(style)
    tts_config = style_def["tts"] if style_def else {}

    audio_path = synthesize_to_file(
        resp.text,
        voice=tts_config.get("voice", "zh-CN-XiaoyiNeural"),
        rate=tts_config.get("rate", "+0%"),
        pitch=tts_config.get("pitch", "+0Hz"),
    )
    if audio_path:
        play_audio(audio_path)


def handle_stop_event(data: dict, user_config: dict = None) -> None:
    """Handle Stop event: block + inject context to trigger subagent."""
    from voice_buddy.injector import process_stop_event
    process_stop_event(data, user_config)


def run() -> None:
    """Read hook JSON from stdin and process."""
    # Setup debug logging — write to config dir, not user home
    from voice_buddy.config import get_config_dir
    log_dir = get_config_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = str(log_dir / "voice-buddy-debug.log")
    logging.basicConfig(
        filename=log_path,
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception as e:
        logger.debug(f"Failed to read stdin: {e}")
        return

    logger.debug(f"Hook event: {data.get('hook_event_name', 'unknown')}")

    try:
        handle_hook_event(data)
    except SystemExit:
        raise  # Let sys.exit(2) propagate for Stop hook blocking
    except Exception as e:
        logger.debug(f"Error handling event: {e}")
