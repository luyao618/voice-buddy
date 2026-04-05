import json
import os
import shutil
from pathlib import Path
from voice_buddy.cli import do_setup, do_uninstall


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
    assert "Stop" in settings["hooks"]


def test_setup_uses_nested_matcher_group_format(tmp_path):
    """Verify hooks use the correct nested format: [{matcher?, hooks: [{type, command}]}]"""
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    repo_path = Path(__file__).parent.parent

    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))

    settings = json.loads((project_dir / ".claude" / "settings.json").read_text())

    # Each event should have a list of matcher groups
    for event_name in ["SessionStart", "SessionEnd", "PostToolUse", "PostToolUseFailure", "Stop"]:
        matcher_groups = settings["hooks"][event_name]
        assert len(matcher_groups) >= 1
        vb_group = [g for g in matcher_groups if g.get("_voice_buddy")][0]
        # Must have "hooks" key containing a list of hook commands
        assert "hooks" in vb_group
        assert isinstance(vb_group["hooks"], list)
        assert len(vb_group["hooks"]) == 1
        hook_cmd = vb_group["hooks"][0]
        assert hook_cmd["type"] == "command"
        assert "voice_buddy" in hook_cmd["command"]
        assert hook_cmd["timeout"] == 5000
        assert hook_cmd["async"] is True


def test_setup_pretooluse_has_matcher(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / ".claude").mkdir()

    repo_path = Path(__file__).parent.parent

    do_setup(project_dir=str(project_dir), repo_path=str(repo_path))

    settings = json.loads((project_dir / ".claude" / "settings.json").read_text())

    pretooluse_groups = settings["hooks"]["PreToolUse"]
    vb_group = [g for g in pretooluse_groups if g.get("_voice_buddy")][0]
    assert vb_group.get("matcher") == "Bash"


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

    agent_path = project_dir / ".claude" / "agents" / "voice-buddy.md"
    assert agent_path.exists()

    content = agent_path.read_text()
    assert "<repo_path>" not in content  # placeholder should be replaced
    # Path may be shlex-quoted, so check the raw path string is present
    assert str(repo_path) in content or str(repo_path).replace("'", "") in content


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

    agent_path = project_dir / ".claude" / "agents" / "voice-buddy.md"
    assert agent_path.exists()

    do_uninstall(project_dir=str(project_dir))
    assert not agent_path.exists()
