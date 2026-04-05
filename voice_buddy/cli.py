"""CLI commands: setup, uninstall, test."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent

_HOOK_EVENTS = [
    "SessionStart",
    "SessionEnd",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "Stop",
]


def _make_matcher_group(repo_path: str, event: str) -> dict:
    """Create a matcher group dict for the given event.

    Claude Code settings.json uses nested format:
      hooks[event] = [{ matcher?: string, hooks: [{ type, command, ... }] }]
    """
    import shlex
    quoted_path = shlex.quote(repo_path)

    hook_cmd = {
        "type": "command",
        "command": f"PYTHONPATH={quoted_path} python3 -m voice_buddy",
        "timeout": 5000,
        "async": True,
    }

    matcher_group = {
        "hooks": [hook_cmd],
        "_voice_buddy": True,  # Marker for reliable uninstall
    }

    if event == "PreToolUse":
        matcher_group["matcher"] = "Bash"

    return matcher_group


def do_setup(project_dir: str = ".", repo_path: str | None = None) -> None:
    """Install voice-buddy hooks into a project's .claude/settings.json."""
    project_dir = os.path.abspath(project_dir)
    if repo_path is None:
        repo_path = str(_REPO_ROOT)
    repo_path = os.path.abspath(repo_path)

    claude_dir = os.path.join(project_dir, ".claude")
    settings_path = os.path.join(claude_dir, "settings.json")

    # Load or create settings
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
    else:
        os.makedirs(claude_dir, exist_ok=True)
        settings = {}

    # Ensure hooks dict exists
    if "hooks" not in settings:
        settings["hooks"] = {}

    # Add matcher groups for each event
    for event in _HOOK_EVENTS:
        if event not in settings["hooks"]:
            settings["hooks"][event] = []

        # Don't add duplicate voice-buddy matcher groups
        existing_vb = [g for g in settings["hooks"][event] if g.get("_voice_buddy")]
        if not existing_vb:
            settings["hooks"][event].append(_make_matcher_group(repo_path, event))

    # Write settings
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    # Copy agent file
    agents_dir = os.path.join(claude_dir, "agents")
    os.makedirs(agents_dir, exist_ok=True)

    agent_src = os.path.join(repo_path, "agent", "voice-buddy.md")
    agent_dst = os.path.join(agents_dir, "voice-buddy.md")

    if os.path.exists(agent_src):
        import shlex
        quoted_path = shlex.quote(repo_path)
        with open(agent_src, "r", encoding="utf-8") as f:
            content = f.read()
        content = content.replace("<repo_path>", quoted_path)
        with open(agent_dst, "w", encoding="utf-8") as f:
            f.write(content)

    print(f"Voice Buddy installed to {project_dir}")
    print(f"  Hooks: {settings_path}")
    print(f"  Agent: {agent_dst}")


def do_uninstall(project_dir: str = ".") -> None:
    """Remove voice-buddy hooks from a project's .claude/settings.json."""
    project_dir = os.path.abspath(project_dir)
    settings_path = os.path.join(project_dir, ".claude", "settings.json")

    if not os.path.exists(settings_path):
        print("No .claude/settings.json found, nothing to uninstall.", file=sys.stderr)
        return

    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    # Remove voice-buddy matcher groups (identified by _voice_buddy marker)
    hooks = settings.get("hooks", {})
    for event in list(hooks.keys()):
        hooks[event] = [g for g in hooks[event] if not g.get("_voice_buddy")]

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    # Remove agent file
    agent_path = os.path.join(project_dir, ".claude", "agents", "voice-buddy.md")
    if os.path.exists(agent_path):
        os.remove(agent_path)

    print(f"Voice Buddy uninstalled from {project_dir}")


def do_test(event: str) -> None:
    """Simulate a hook event and run the full pipeline."""
    from voice_buddy.main import handle_hook_event

    mock_data = {
        "sessionstart": {
            "hook_event_name": "SessionStart",
            "source": "startup",
            "session_id": "test",
            "cwd": os.getcwd(),
        },
        "sessionend": {
            "hook_event_name": "SessionEnd",
            "session_id": "test",
            "cwd": os.getcwd(),
        },
        "pretooluse": {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m 'test commit'"},
        },
        "posttooluse": {
            "hook_event_name": "PostToolUse",
            "inputs": {"command": "python -m pytest tests/ -v"},
            "response": "===== 10 passed in 1.23s =====",
        },
        "posttoolusefailure": {
            "hook_event_name": "PostToolUseFailure",
            "tool_name": "Bash",
            "error": "Command failed with exit code 1",
            "error_type": "command_error",
        },
    }

    event_lower = event.lower()

    # Special handling for stop: create a real mock transcript
    if event_lower == "stop":
        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8",
        )
        tmp.write('{"role": "user", "content": "fix the bug in parser.py"}\n')
        tmp.write('{"role": "assistant", "content": "I have fixed the bug in parser.py and updated the tests. All 12 tests pass now."}\n')
        tmp.close()
        mock_data["stop"] = {
            "hook_event_name": "Stop",
            "transcript_path": tmp.name,
            "session_id": "test",
            "cwd": os.getcwd(),
        }

    if event_lower not in mock_data:
        print(f"Unknown event: {event}", file=sys.stderr)
        print(f"Available: {', '.join(mock_data.keys())}", file=sys.stderr)
        sys.exit(1)

    data = mock_data[event_lower]
    print(f"Testing event: {data['hook_event_name']}")

    if event_lower == "stop":
        print("(Stop event: testing injector path only, outputs additionalContext JSON)")

    handle_hook_event(data)
    print("Done!")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="voice-buddy",
        description="Voice Buddy - personality-driven voice companion for Claude Code",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # setup
    setup_parser = subparsers.add_parser("setup", help="Install hooks to a project")
    setup_parser.add_argument(
        "--global", dest="is_global", action="store_true",
        help="Install to ~/.claude/ instead of project .claude/",
    )
    setup_parser.add_argument(
        "--project", dest="project_dir", default=None,
        help="Target project directory (default: current directory)",
    )

    # uninstall
    uninstall_parser = subparsers.add_parser("uninstall", help="Remove hooks from a project")
    uninstall_parser.add_argument(
        "--global", dest="is_global", action="store_true",
        help="Uninstall from ~/.claude/ instead of project .claude/",
    )
    uninstall_parser.add_argument(
        "--project", dest="project_dir", default=None,
        help="Target project directory (default: current directory)",
    )

    # test
    test_parser = subparsers.add_parser("test", help="Test a hook event")
    test_parser.add_argument("event", help="Event name to test")

    args = parser.parse_args()

    if args.command == "setup":
        if args.is_global:
            project_dir = os.path.expanduser("~")
        elif args.project_dir:
            project_dir = args.project_dir
        else:
            project_dir = "."
        do_setup(project_dir=project_dir)
    elif args.command == "uninstall":
        if args.is_global:
            project_dir = os.path.expanduser("~")
        elif args.project_dir:
            project_dir = args.project_dir
        else:
            project_dir = "."
        do_uninstall(project_dir=project_dir)
    elif args.command == "test":
        do_test(args.event)


if __name__ == "__main__":
    main()
