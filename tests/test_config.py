import json
import os
import platform
from pathlib import Path
from unittest.mock import patch

from voice_buddy.config import (
    get_config_dir,
    load_user_config,
    save_user_config,
    DEFAULT_CONFIG,
)


def test_get_config_dir_returns_path():
    result = get_config_dir()
    assert isinstance(result, Path)
    assert "voice-buddy" in str(result)


def test_get_config_dir_macos():
    with patch("platform.system", return_value="Darwin"):
        result = get_config_dir()
        assert "Library/Application Support/voice-buddy" in str(result)


def test_get_config_dir_linux():
    with patch("platform.system", return_value="Linux"), \
         patch.dict(os.environ, {"XDG_CONFIG_HOME": ""}, clear=False):
        result = get_config_dir()
        assert ".config/voice-buddy" in str(result)


def test_get_config_dir_linux_xdg():
    with patch("platform.system", return_value="Linux"), \
         patch.dict(os.environ, {"XDG_CONFIG_HOME": "/custom/config"}, clear=False):
        result = get_config_dir()
        assert str(result) == "/custom/config/voice-buddy"


def test_get_config_dir_windows():
    with patch("platform.system", return_value="Windows"), \
         patch.dict(os.environ, {"APPDATA": "C:\\Users\\test\\AppData\\Roaming"}, clear=False):
        result = get_config_dir()
        assert "AppData" in str(result)
        assert "voice-buddy" in str(result)


def test_default_config_has_required_fields():
    assert DEFAULT_CONFIG["style"] == "cute-girl"
    assert DEFAULT_CONFIG["nickname"] == "Master"
    assert DEFAULT_CONFIG["enabled"] is True
    assert DEFAULT_CONFIG["events"]["sessionstart"] is True
    assert DEFAULT_CONFIG["events"]["sessionend"] is True
    assert DEFAULT_CONFIG["events"]["notification"] is True
    assert DEFAULT_CONFIG["events"]["stop"] is True
    assert DEFAULT_CONFIG["persona_override"] is None


def test_load_user_config_creates_default_on_first_run(tmp_path):
    config_path = tmp_path / "config.json"
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        config = load_user_config()
    assert config == DEFAULT_CONFIG
    assert config_path.exists()
    saved = json.loads(config_path.read_text())
    assert saved == DEFAULT_CONFIG


def test_load_user_config_reads_existing(tmp_path):
    config_path = tmp_path / "config.json"
    custom = {
        "style": "kawaii",
        "nickname": "Senpai",
        "enabled": True,
        "events": {
            "sessionstart": True,
            "sessionend": False,
            "notification": True,
            "stop": True,
        },
        "persona_override": None,
    }
    config_path.write_text(json.dumps(custom))
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        config = load_user_config()
    assert config["style"] == "kawaii"
    assert config["nickname"] == "Senpai"
    assert config["events"]["sessionend"] is False


def test_load_user_config_fills_missing_fields(tmp_path):
    config_path = tmp_path / "config.json"
    partial = {"style": "warm-boy"}
    config_path.write_text(json.dumps(partial))
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        config = load_user_config()
    assert config["style"] == "warm-boy"
    assert config["nickname"] == "Master"  # filled from default
    assert config["enabled"] is True  # filled from default


def test_save_user_config_writes_json(tmp_path):
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        save_user_config({"style": "secretary", "nickname": "Boss",
                          "enabled": True,
                          "events": {"sessionstart": True, "sessionend": True,
                                     "notification": True, "stop": True},
                          "persona_override": None})
    saved = json.loads((tmp_path / "config.json").read_text())
    assert saved["style"] == "secretary"
    assert saved["nickname"] == "Boss"


def test_load_user_config_uses_plugin_env_vars_on_first_run(tmp_path):
    """When no config exists, CLAUDE_PLUGIN_OPTION_* env vars set defaults."""
    env = {
        "CLAUDE_PLUGIN_OPTION_STYLE": "kawaii",
        "CLAUDE_PLUGIN_OPTION_NICKNAME": "Senpai",
    }
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path), \
         patch.dict(os.environ, env, clear=False):
        config = load_user_config()
    assert config["style"] == "kawaii"
    assert config["nickname"] == "Senpai"
    # Verify it was persisted
    saved = json.loads((tmp_path / "config.json").read_text())
    assert saved["style"] == "kawaii"
    assert saved["nickname"] == "Senpai"


def test_load_user_config_ignores_env_vars_when_config_exists(tmp_path):
    """Existing config file takes precedence over env vars."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "style": "warm-boy",
        "nickname": "Darling",
        "enabled": True,
        "events": {"sessionstart": True, "sessionend": True,
                   "notification": True, "stop": True},
        "persona_override": None,
    }))
    env = {
        "CLAUDE_PLUGIN_OPTION_STYLE": "kawaii",
        "CLAUDE_PLUGIN_OPTION_NICKNAME": "Senpai",
    }
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path), \
         patch.dict(os.environ, env, clear=False):
        config = load_user_config()
    assert config["style"] == "warm-boy"
    assert config["nickname"] == "Darling"
