import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch
from voice_buddy.cli import do_setup, do_uninstall, do_config, do_on, do_off


def test_setup_creates_settings_json(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    repo_path = Path(__file__).parent.parent  # Voice Buddy repo root

    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))

    settings_path = project_dir / ".claude" / "settings.json"
    assert settings_path.exists()

    settings = json.loads(settings_path.read_text())
    assert "hooks" in settings
    assert "SessionStart" in settings["hooks"]
    assert "SessionEnd" in settings["hooks"]
    assert "Notification" in settings["hooks"]
    assert "Stop" in settings["hooks"]


def test_setup_does_not_register_tooluse_events(tmp_path):
    """ToolUse events should NOT be registered."""
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    repo_path = Path(__file__).parent.parent

    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))

    settings = json.loads((project_dir / ".claude" / "settings.json").read_text())

    assert "PreToolUse" not in settings["hooks"]
    assert "PostToolUse" not in settings["hooks"]
    assert "PostToolUseFailure" not in settings["hooks"]


def test_setup_uses_nested_matcher_group_format(tmp_path):
    """Verify hooks use the correct nested format: [{matcher?, hooks: [{type, command}]}]"""
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    repo_path = Path(__file__).parent.parent

    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))

    settings = json.loads((project_dir / ".claude" / "settings.json").read_text())

    # Async events
    for event_name in ["SessionStart", "SessionEnd", "Notification"]:
        matcher_groups = settings["hooks"][event_name]
        assert len(matcher_groups) >= 1
        vb_group = [g for g in matcher_groups if g.get("_voice_buddy")][0]
        assert "hooks" in vb_group
        assert isinstance(vb_group["hooks"], list)
        assert len(vb_group["hooks"]) == 1
        hook_cmd = vb_group["hooks"][0]
        assert hook_cmd["type"] == "command"
        assert "voice_buddy" in hook_cmd["command"]
        assert hook_cmd["timeout"] == 5000
        assert hook_cmd["async"] is True

    # Stop hook must be synchronous
    stop_groups = settings["hooks"]["Stop"]
    stop_vb = [g for g in stop_groups if g.get("_voice_buddy")][0]
    assert stop_vb["hooks"][0]["async"] is False


def test_setup_preserves_existing_hooks(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    existing_settings = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "",
                    "hooks": [
                        {"type": "command", "command": "echo existing", "timeout": 3000}
                    ]
                }
            ]
        }
    }
    (project_dir / ".claude" / "settings.json").write_text(json.dumps(existing_settings))

    repo_path = Path(__file__).parent.parent

    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))

    settings = json.loads((project_dir / ".claude" / "settings.json").read_text())

    session_groups = settings["hooks"]["SessionStart"]
    assert len(session_groups) == 2  # existing + voice buddy
    assert session_groups[0]["hooks"][0]["command"] == "echo existing"


def test_setup_copies_agent_file(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    repo_path = Path(__file__).parent.parent

    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))

    agents_dir = project_dir / ".claude" / "agents"
    # All 7 persona agent files should be copied
    expected = [
        "voice-buddy-cute-girl.md",
        "voice-buddy-elegant-lady.md",
        "voice-buddy-warm-boy.md",
        "voice-buddy-secretary.md",
        "voice-buddy-steward.md",
        "voice-buddy-cyber-girl.md",
        "voice-buddy-kawaii.md",
    ]
    for fname in expected:
        agent_path = agents_dir / fname
        assert agent_path.exists(), f"Missing agent file: {fname}"


def test_uninstall_removes_hooks(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    repo_path = Path(__file__).parent.parent

    # Setup first
    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))
    # Then uninstall
    do_uninstall(project_dir=str(project_dir))

    settings = json.loads((project_dir / ".claude" / "settings.json").read_text())

    # All hook lists should have no voice buddy matcher groups
    for event_name, groups in settings["hooks"].items():
        for group in groups:
            assert group.get("_voice_buddy") is not True


def test_uninstall_preserves_other_hooks(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    existing_settings = {
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "",
                    "hooks": [
                        {"type": "command", "command": "echo existing", "timeout": 3000}
                    ]
                }
            ]
        }
    }
    (project_dir / ".claude" / "settings.json").write_text(json.dumps(existing_settings))

    repo_path = Path(__file__).parent.parent

    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))
    do_uninstall(project_dir=str(project_dir))

    settings = json.loads((project_dir / ".claude" / "settings.json").read_text())

    session_groups = settings["hooks"]["SessionStart"]
    assert len(session_groups) == 1
    assert session_groups[0]["hooks"][0]["command"] == "echo existing"


def test_uninstall_removes_agent_file(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    repo_path = Path(__file__).parent.parent

    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))

    agents_dir = project_dir / ".claude" / "agents"
    # Verify at least one agent file was installed before uninstalling
    installed = list(agents_dir.glob("voice-buddy-*.md"))
    assert len(installed) > 0, "Expected agent files to be installed"

    do_uninstall(project_dir=str(project_dir))

    # All voice-buddy agent files should be removed
    remaining = list(agents_dir.glob("voice-buddy-*.md"))
    assert len(remaining) == 0, f"Expected all agent files removed, found: {remaining}"


def test_do_config_set_style(tmp_path):
    config_path = tmp_path / "config.json"
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        do_config(style="kawaii")
    saved = json.loads(config_path.read_text())
    assert saved["style"] == "kawaii"


def test_do_config_set_nickname(tmp_path):
    config_path = tmp_path / "config.json"
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        do_config(nickname="Senpai")
    saved = json.loads(config_path.read_text())
    assert saved["nickname"] == "Senpai"


def test_do_config_set_multiple(tmp_path):
    config_path = tmp_path / "config.json"
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        do_config(style="secretary", nickname="Boss")
    saved = json.loads(config_path.read_text())
    assert saved["style"] == "secretary"
    assert saved["nickname"] == "Boss"


def test_do_config_disable_event(tmp_path):
    config_path = tmp_path / "config.json"
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        do_config(disable="notification")
    saved = json.loads(config_path.read_text())
    assert saved["events"]["notification"] is False


def test_do_config_enable_event(tmp_path):
    config_path = tmp_path / "config.json"
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        do_config(disable="notification")
        do_config(enable="notification")
    saved = json.loads(config_path.read_text())
    assert saved["events"]["notification"] is True


def test_do_on(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"style": "cute-girl", "nickname": "Master",
                                        "enabled": False,
                                        "events": {"sessionstart": True, "sessionend": True,
                                                    "notification": True, "stop": True},
                                        "persona_override": None}))
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        do_on()
    saved = json.loads(config_path.read_text())
    assert saved["enabled"] is True


def test_do_off(tmp_path):
    config_path = tmp_path / "config.json"
    with patch("voice_buddy.config.get_config_dir", return_value=tmp_path):
        do_off()
    saved = json.loads(config_path.read_text())
    assert saved["enabled"] is False
