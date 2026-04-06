# tests/test_plugin.py
import json
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def test_plugin_json_exists():
    path = REPO_ROOT / ".claude-plugin" / "plugin.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["name"] == "voice-buddy"
    assert "version" in data


def test_marketplace_json_exists():
    path = REPO_ROOT / ".claude-plugin" / "marketplace.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["name"] == "voice-buddy-marketplace"


def test_hooks_json_exists_and_valid():
    path = REPO_ROOT / "hooks" / "hooks.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert "hooks" in data
    assert "SessionStart" in data["hooks"]
    assert "SessionEnd" in data["hooks"]
    assert "Notification" in data["hooks"]
    assert "Stop" in data["hooks"]
    # Stop must be synchronous
    stop_hook = data["hooks"]["Stop"][0]["hooks"][0]
    assert stop_hook["async"] is False
    # Others must be async
    start_hook = data["hooks"]["SessionStart"][0]["hooks"][0]
    assert start_hook["async"] is True


def test_all_persona_files_exist():
    personas_dir = REPO_ROOT / "personas"
    expected = ["cute-girl", "elegant-lady", "warm-boy", "secretary", "kawaii"]
    for style_id in expected:
        path = personas_dir / f"{style_id}.json"
        assert path.exists(), f"Missing persona: {style_id}"


def test_all_template_files_exist():
    templates_dir = REPO_ROOT / "templates"
    expected = ["cute-girl", "elegant-lady", "warm-boy", "secretary", "kawaii"]
    for style_id in expected:
        path = templates_dir / f"{style_id}.json"
        assert path.exists(), f"Missing template: {style_id}"


def test_all_agent_files_exist():
    agents_dir = REPO_ROOT / "agents"
    expected = [
        "voice-buddy-cute-girl",
        "voice-buddy-elegant-lady",
        "voice-buddy-warm-boy",
        "voice-buddy-secretary",
        "voice-buddy-kawaii",
    ]
    for name in expected:
        path = agents_dir / f"{name}.md"
        assert path.exists(), f"Missing agent: {name}"


def test_all_prepackaged_audio_dirs_exist():
    audio_dir = REPO_ROOT / "assets" / "audio"
    expected = ["cute-girl", "elegant-lady", "warm-boy", "secretary", "kawaii"]
    for style_id in expected:
        path = audio_dir / style_id
        assert path.exists(), f"Missing audio dir: {style_id}"


def test_bin_wrapper_exists_and_executable():
    path = REPO_ROOT / "bin" / "voice-buddy"
    assert path.exists(), "Missing bin/voice-buddy wrapper"
    import os
    assert os.access(path, os.X_OK), "bin/voice-buddy is not executable"


def test_plugin_json_has_user_config():
    path = REPO_ROOT / ".claude-plugin" / "plugin.json"
    data = json.loads(path.read_text())
    assert "userConfig" in data
    assert "style" in data["userConfig"]
    assert "nickname" in data["userConfig"]
    assert data["userConfig"]["style"]["sensitive"] is False
    assert data["userConfig"]["nickname"]["sensitive"] is False


def test_slash_command_exists():
    path = REPO_ROOT / "commands" / "voice-buddy.md"
    assert path.exists()
    content = path.read_text()
    assert "voice-buddy config" in content
