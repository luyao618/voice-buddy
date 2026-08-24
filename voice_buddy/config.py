"""Cross-platform user configuration for Voice Buddy."""

import copy
import json
import os
import platform
import tempfile
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
    # Hotkey-stop feature (macOS only). hotkey is an F-key name (F1..F12).
    "hotkey": "F2",
    "hotkey_enabled": True,
    # Cached path of the python interpreter that was last granted Accessibility.
    # Used by hotkey-doctor to detect drift on venv recreate / Python upgrade.
    "last_trusted_executable": None,
}

_REPO_ROOT = Path(__file__).parent.parent


def _write_config_atomic(config_path: Path, config: dict) -> None:
    """Persist config without exposing a partial destination file."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix="config.", suffix=".tmp", dir=str(config_path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, config_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


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
        _write_config_atomic(config_path, defaults)
        return defaults


def save_user_config(config: dict) -> None:
    """Atomically save user config to disk."""
    _write_config_atomic(get_config_dir() / "config.json", config)


def get_repo_root() -> Path:
    """Return the repo/plugin root directory."""
    return _REPO_ROOT
