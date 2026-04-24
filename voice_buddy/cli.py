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
    "Notification",
    "Stop",
]


def _make_matcher_group(repo_path: str, event: str) -> dict:
    """Create a matcher group dict for the given event.

    Claude Code settings.json uses nested format:
      hooks[event] = [{ matcher?: string, hooks: [{ type, command, ... }] }]
    """
    import shlex
    quoted_path = shlex.quote(repo_path)

    # Stop hook must be synchronous so Claude reads the decision + additionalContext.
    # All other hooks are async to avoid blocking Claude.
    is_async = event != "Stop"

    hook_cmd = {
        "type": "command",
        "command": f"PYTHONPATH={quoted_path} python3 -m voice_buddy",
        "timeout": 5000,
        "async": is_async,
    }

    matcher_group = {
        "hooks": [hook_cmd],
        "_voice_buddy": True,  # Marker for reliable uninstall
    }

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

    # Copy all agent persona files from agents/ directory
    agents_dir = os.path.join(claude_dir, "agents")
    os.makedirs(agents_dir, exist_ok=True)

    agents_src_dir = os.path.join(repo_path, "agents")
    copied = []
    if os.path.isdir(agents_src_dir):
        for fname in os.listdir(agents_src_dir):
            if fname.startswith("voice-buddy-") and fname.endswith(".md"):
                src = os.path.join(agents_src_dir, fname)
                dst = os.path.join(agents_dir, fname)
                with open(src, "r", encoding="utf-8") as f:
                    content = f.read()
                with open(dst, "w", encoding="utf-8") as f:
                    f.write(content)
                copied.append(fname)

    print(f"Voice Buddy installed to {project_dir}")
    print(f"  Hooks: {settings_path}")
    for fname in sorted(copied):
        print(f"  Agent: {os.path.join(agents_dir, fname)}")


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

    # Remove all voice-buddy agent persona files
    agents_dir = os.path.join(project_dir, ".claude", "agents")
    if os.path.isdir(agents_dir):
        for fname in os.listdir(agents_dir):
            if fname.startswith("voice-buddy-") and fname.endswith(".md"):
                os.remove(os.path.join(agents_dir, fname))

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
        "notification": {
            "hook_event_name": "Notification",
            "message": "Claude has a question for you",
            "title": "Claude Code",
            "notification_type": "question",
            "session_id": "test",
            "cwd": os.getcwd(),
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

    try:
        handle_hook_event(data)
    except SystemExit:
        pass  # Expected: injector calls sys.exit(2) on trigger
    finally:
        # Clean up temp transcript file for stop events
        if event_lower == "stop":
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
    print("Done!")


def do_config(
    style: str | None = None,
    nickname: str | None = None,
    disable: str | None = None,
    enable: str | None = None,
    edit_persona: bool = False,
) -> None:
    """Update user configuration."""
    from voice_buddy.config import load_user_config, save_user_config

    config = load_user_config()

    if style is not None:
        from voice_buddy.styles import load_style
        if load_style(style) is None:
            print(f"Unknown style: {style}", file=sys.stderr)
            return
        config["style"] = style

    if nickname is not None:
        config["nickname"] = nickname

    if disable is not None:
        if disable in config["events"]:
            config["events"][disable] = False
        else:
            print(f"Unknown event: {disable}", file=sys.stderr)
            return

    if enable is not None:
        if enable in config["events"]:
            config["events"][enable] = True
        else:
            print(f"Unknown event: {enable}", file=sys.stderr)
            return

    if edit_persona:
        import subprocess
        import tempfile
        editor = os.environ.get("EDITOR", "vi")
        current = config.get("persona_override") or ""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(current)
            f.flush()
            subprocess.call([editor, f.name])
        with open(f.name, "r") as rf:
            new_persona = rf.read().strip()
        config["persona_override"] = new_persona if new_persona else None
        os.unlink(f.name)

    save_user_config(config)
    print(f"Config updated: style={config['style']}, nickname={config['nickname']}")


def do_on() -> None:
    """Enable voice buddy globally."""
    from voice_buddy.config import load_user_config, save_user_config
    from voice_buddy import coord
    config = load_user_config()
    config["enabled"] = True
    save_user_config(config)
    coord.reload_listener_config()
    print("Voice Buddy: ON")


def do_off() -> None:
    """Disable voice buddy globally."""
    from voice_buddy.config import load_user_config, save_user_config
    from voice_buddy import coord
    config = load_user_config()
    config["enabled"] = False
    save_user_config(config)
    # Live-reload listener if running.
    coord.reload_listener_config()
    print("Voice Buddy: OFF")


def do_stop() -> int:
    """CLI fallback: SIGTERM all currently-playing audio subprocesses."""
    from voice_buddy import playback_pids
    killed = playback_pids.kill_all()
    print(f"Stopped {killed} playback process(es).")
    return 0


def do_set_hotkey(hotkey: str | None = None,
                  disable: bool = False,
                  enable: bool = False) -> int:
    """Update hotkey config and live-reload the listener."""
    from voice_buddy.config import load_user_config, save_user_config
    from voice_buddy.keymap import is_supported, SUPPORTED_KEYS
    from voice_buddy import coord

    config = load_user_config()
    changed = False

    if hotkey is not None:
        if not is_supported(hotkey):
            print(
                f"Unsupported hotkey: {hotkey!r}. "
                f"Supported: {', '.join(SUPPORTED_KEYS)}",
                file=sys.stderr,
            )
            return 2
        config["hotkey"] = hotkey.upper()
        changed = True

    if disable:
        config["hotkey_enabled"] = False
        changed = True
    if enable:
        config["hotkey_enabled"] = True
        changed = True

    if not changed:
        print(
            f"hotkey={config.get('hotkey', 'F2')} "
            f"enabled={config.get('hotkey_enabled', True)}"
        )
        return 0

    save_user_config(config)
    reloaded = coord.reload_listener_config()
    suffix = " (listener reloaded)" if reloaded else " (no live listener)"
    print(
        f"hotkey={config['hotkey']} enabled={config['hotkey_enabled']}{suffix}"
    )
    return 0


def do_hotkey_doctor(non_interactive: bool = False, as_json: bool = False) -> int:
    from voice_buddy.hotkey_doctor import run_doctor
    return run_doctor(non_interactive=non_interactive, as_json=as_json)


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
    test_parser.add_argument("--style", help="Override style for this test")

    # config
    config_parser = subparsers.add_parser("config", help="Configure voice buddy")
    config_parser.add_argument("--style", help="Set style")
    config_parser.add_argument("--nickname", help="Set nickname")
    config_parser.add_argument("--disable", help="Disable an event")
    config_parser.add_argument("--enable", help="Enable an event")
    config_parser.add_argument("--edit-persona", action="store_true", help="Edit agent persona")
    config_parser.add_argument("--hotkey", help="Set global stop hotkey (e.g. F2)")
    config_parser.add_argument("--disable-hotkey", action="store_true",
                               help="Disable the global stop hotkey")
    config_parser.add_argument("--enable-hotkey", action="store_true",
                               help="Enable the global stop hotkey")

    # on / off
    subparsers.add_parser("on", help="Enable voice buddy")
    subparsers.add_parser("off", help="Disable voice buddy")

    # stop
    subparsers.add_parser("stop", help="Immediately stop all currently-playing audio")

    # hotkey-doctor
    doctor_parser = subparsers.add_parser(
        "hotkey-doctor",
        help="Diagnose the global hotkey feature (Accessibility, fn-keys, listener)",
    )
    doctor_parser.add_argument("--non-interactive", action="store_true",
                               help="Skip the interactive F-key press check")
    doctor_parser.add_argument("--json", dest="as_json", action="store_true",
                               help="Emit machine-readable JSON output")

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
    elif args.command == "config":
        # Hotkey-related changes go through do_set_hotkey; classic style/nickname/event
        # changes go through do_config. Both can be combined in a single invocation.
        has_config_args = (args.style is not None or args.nickname is not None
                          or args.disable is not None or args.enable is not None
                          or args.edit_persona)
        has_hotkey_args = (args.hotkey is not None or args.disable_hotkey or args.enable_hotkey)

        if not has_config_args and not has_hotkey_args:
            # No arguments: show current config
            from voice_buddy.config import load_user_config
            cfg = load_user_config()
            print(f"style={cfg['style']}")
            print(f"nickname={cfg['nickname']}")
            print(f"enabled={cfg['enabled']}")
            print(f"events={cfg['events']}")
            print(f"hotkey={cfg.get('hotkey', 'F2')} enabled={cfg.get('hotkey_enabled', True)}")
        else:
            if has_hotkey_args:
                rc = do_set_hotkey(
                    hotkey=args.hotkey,
                    disable=args.disable_hotkey,
                    enable=args.enable_hotkey,
                )
                if rc != 0:
                    sys.exit(rc)
            if has_config_args:
                do_config(style=args.style, nickname=args.nickname,
                          disable=args.disable, enable=args.enable,
                          edit_persona=args.edit_persona)
    elif args.command == "on":
        do_on()
    elif args.command == "off":
        do_off()
    elif args.command == "stop":
        sys.exit(do_stop())
    elif args.command == "hotkey-doctor":
        sys.exit(do_hotkey_doctor(
            non_interactive=args.non_interactive,
            as_json=args.as_json,
        ))


if __name__ == "__main__":
    main()
