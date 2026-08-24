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


def _atomic_write_json(path: Path, value: dict) -> None:
    """Durably write JSON before atomically replacing the destination."""
    fd, tmp_path = tempfile.mkstemp(
        prefix=f"{path.stem}.", suffix=".tmp", dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
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
        config_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(config_path, defaults)
        return defaults


def save_user_config(config: dict) -> None:
    """Save user config to disk."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.json"
    _atomic_write_json(config_path, config)


def get_repo_root() -> Path:
    """Return the repo/plugin root directory."""
    return _REPO_ROOT


# Runtime resources live at the plugin root, not inside the Python package.
# Under the supported install paths — Claude plugin, editable checkout — the
# package's parent *is* that root, so this resolves correctly and there is a
# single source of truth. A standalone wheel install has no plugin root: the
# parent is site-packages/, these directories are absent, and every lookup
# silently returns None. That surface is deliberately unsupported (see README
# "Distribution contract"); this check is what lets callers say so out loud
# rather than behave like a voice companion with nothing to say.
_RUNTIME_RESOURCE_DIRS = ("personas", "templates", "assets")

INSTALL_HELP = (
    "Voice Buddy's runtime resources (personas/, templates/, assets/) were not "
    "found next to the installed package.\n"
    "Standalone `pip install` is not a supported installation method — the "
    "personas, templates, audio assets, hooks and agents are all delivered by "
    "the Claude Code plugin, not the wheel.\n"
    "Install it as a plugin instead:\n"
    "  /plugin marketplace add luyao618/voice-buddy\n"
    "  /plugin install voice-buddy\n"
    "Or, for development, from a checkout:\n"
    "  pip install -c constraints.txt -e \".[dev]\""
)


def missing_runtime_resources() -> list[str]:
    """Return the runtime resource directories absent from the install root.

    Empty means every resource the voice path needs is present.
    """
    root = get_repo_root()
    return [name for name in _RUNTIME_RESOURCE_DIRS if not (root / name).is_dir()]
