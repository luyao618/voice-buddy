"""Cross-platform user configuration for Voice Buddy."""

import copy
import json
import os
import platform
from pathlib import Path

DEFAULT_CONFIG = {
    "style": "cute-girl",
    "nickname": "Master",
    "enabled": True,
    "events": {
        "sessionstart": True,
        "sessionend": True,
        "notification": True,
        "stop": True,
    },
    "persona_override": None,
}

_REPO_ROOT = Path(__file__).parent.parent


def get_config_dir() -> Path:
    """Return the platform-appropriate config directory for voice-buddy."""
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "voice-buddy"
    elif system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "voice-buddy"
        return Path.home() / "AppData" / "Roaming" / "voice-buddy"
    else:  # Linux and others
        xdg = os.environ.get("XDG_CONFIG_HOME", "")
        if xdg:
            return Path(xdg) / "voice-buddy"
        return Path.home() / ".config" / "voice-buddy"


def load_user_config() -> dict:
    """Load user config, creating defaults if missing."""
    config_dir = get_config_dir()
    config_path = config_dir / "config.json"

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        # Fill missing fields from defaults
        merged = {**DEFAULT_CONFIG, **user_config}
        merged["events"] = {**DEFAULT_CONFIG["events"], **user_config.get("events", {})}
        return merged
    else:
        # First run: create defaults, applying plugin userConfig env vars if set
        defaults = copy.deepcopy(DEFAULT_CONFIG)
        env_style = os.environ.get("CLAUDE_PLUGIN_OPTION_STYLE")
        env_nickname = os.environ.get("CLAUDE_PLUGIN_OPTION_NICKNAME")
        if env_style:
            defaults["style"] = env_style
        if env_nickname:
            defaults["nickname"] = env_nickname
        config_dir.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(defaults, f, indent=2, ensure_ascii=False)
        return defaults


def save_user_config(config: dict) -> None:
    """Save user config to disk."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def get_repo_root() -> Path:
    """Return the repo/plugin root directory."""
    return _REPO_ROOT

