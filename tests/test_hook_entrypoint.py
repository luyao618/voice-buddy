# tests/test_hook_entrypoint.py
"""End-to-end contract tests through the real `python -m voice_buddy` entry point.

The in-process tests in test_hook_contracts.py call `process_stop_event`
directly, so they can only observe the exit code. That is not enough for the
Stop contract: Claude Code reads the block *reason* from stderr, so a change
that dropped the message, emitted it empty, or sent it to stdout would keep
every exit-code assertion green while breaking the integration.

These tests spawn the module as a subprocess with an isolated HOME, feed real
payloads on stdin, and assert on exit code, stdout and stderr separately.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


@pytest.fixture
def hook_env(tmp_path):
    """Isolated HOME with an enabled config, so nothing touches the real one."""
    home = tmp_path / "home"
    cfg_dir = home / "Library" / "Application Support" / "voice-buddy"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.json").write_text(json.dumps({
        "style": "cute-girl",
        "nickname": "Master",
        "enabled": True,
        "events": {"sessionstart": True, "sessionend": True,
                   "notification": True, "stop": True},
        # Keep the macOS hotkey listener out of the subprocess.
        "hotkey_enabled": False,
    }))
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("XDG_CONFIG_HOME", None)
    return env


def run_hook(payload, env, raw=None):
    """Feed a payload to the real entry point. Returns CompletedProcess."""
    stdin = raw if raw is not None else json.dumps(payload)
    return subprocess.run(
        [sys.executable, "-m", "voice_buddy"],
        input=stdin, env=env, cwd=str(REPO_ROOT),
        capture_output=True, text=True, timeout=60,
    )


STOP_COMPLETED = {
    "session_id": "abc123",
    "transcript_path": "/tmp/nonexistent.jsonl",
    "cwd": "/tmp",
    "permission_mode": "default",
    "hook_event_name": "Stop",
    "stop_hook_active": False,
    "last_assistant_message": "I fixed the bug and updated the tests.",
}


# --- Stop: the synchronous decision contract, observed for real -------------

def test_stop_first_call_exits_2_with_reason_on_stderr(hook_env):
    """First call blocks: exit 2, non-empty reason on stderr.

    Exit 2 is how Claude Code is told to keep going, and it reads the reason
    from stderr. Asserting the code alone would still pass if the message were
    dropped or emitted empty.
    """
    proc = run_hook(STOP_COMPLETED, hook_env)
    assert proc.returncode == 2
    assert proc.stderr.strip(), "block reason must be non-empty on stderr"
    # It must be the actual instruction, not incidental noise.
    assert "Voice Buddy" in proc.stderr


def test_stop_block_reason_is_not_on_stdout(hook_env):
    """stdout must not carry the reason.

    Claude Code parses stdout as optional JSON hook output; the reason belongs
    on stderr. Routing it to stdout would break the contract while leaving the
    exit code correct.
    """
    proc = run_hook(STOP_COMPLETED, hook_env)
    assert proc.returncode == 2
    assert "Voice Buddy" not in proc.stdout
    assert "REQUIRED ACTION" not in proc.stdout


def test_stop_reentrant_call_exits_0_and_emits_no_reason(hook_env):
    """Second call, with stop_hook_active=true, must allow the stop.

    This is the loop guard: Claude Code sets the flag once it is already
    continuing because of a stop hook, and blocking again would spin.
    """
    proc = run_hook({**STOP_COMPLETED, "stop_hook_active": True}, hook_env)
    assert proc.returncode == 0
    assert "Voice Buddy" not in proc.stderr
    assert "REQUIRED ACTION" not in proc.stderr
    assert "Voice Buddy" not in proc.stdout


def test_stop_block_then_reentry_terminates(hook_env):
    """The full documented sequence: block once, then stop cleanly."""
    first = run_hook(STOP_COMPLETED, hook_env)
    second = run_hook({**STOP_COMPLETED, "stop_hook_active": True}, hook_env)
    assert (first.returncode, second.returncode) == (2, 0)
    assert first.stderr.strip()
    assert not second.stderr.strip()


def test_stop_without_completion_signal_exits_0(hook_env):
    proc = run_hook(
        {**STOP_COMPLETED, "last_assistant_message": "What next?"}, hook_env)
    assert proc.returncode == 0
    assert not proc.stderr.strip()


# --- Non-disruptive behavior for everything else ----------------------------

@pytest.mark.parametrize("label,payload,raw", [
    ("non-dict payload", None, "[1,2,3]"),
    ("not JSON", None, "this is not json"),
    ("empty stdin", None, ""),
    ("unknown event", {"hook_event_name": "PreToolUse"}, None),
    ("non-string event name", {"hook_event_name": 42}, None),
    ("Stop, non-string message", {"hook_event_name": "Stop",
                                  "last_assistant_message": 123}, None),
    ("Notification, non-string message", {"hook_event_name": "Notification",
                                          "message": 123}, None),
])
def test_malformed_payloads_exit_0_and_stay_quiet(label, payload, raw, hook_env):
    """A payload we can't read must never look like a hook failure.

    Claude Code surfaces a non-zero exit to the user, so anything we don't
    understand exits 0 with nothing on stderr.
    """
    proc = run_hook(payload, hook_env, raw=raw)
    assert proc.returncode == 0, f"{label}: exit {proc.returncode}"
    assert not proc.stderr.strip(), f"{label}: unexpected stderr {proc.stderr!r}"


def test_hostile_event_name_is_not_written_to_the_persistent_log(hook_env):
    """The end-to-end version of the log-hygiene contract.

    The in-process test uses caplog; this one checks the file that actually
    persists on disk, which is what a later reader would see.
    """
    secret = "/Users/victim/.claude/projects/LEAKED_SECRET_hunter2.jsonl"
    proc = run_hook({"hook_event_name": secret}, hook_env)
    assert proc.returncode == 0

    log = (Path(hook_env["HOME"]) / "Library" / "Application Support"
           / "voice-buddy" / "logs" / "voice-buddy-debug.log")
    text = log.read_text() if log.exists() else ""
    assert "LEAKED_SECRET_hunter2" not in text
    assert "/Users/victim" not in text


def test_sensitive_stop_fields_are_not_written_to_the_persistent_log(hook_env):
    secret = "LEAKED_MESSAGE_hunter2"
    proc = run_hook({**STOP_COMPLETED,
                     "last_assistant_message": f"I fixed the bug: {secret}"},
                    hook_env)
    assert proc.returncode == 2  # still blocks; the voice works

    log = (Path(hook_env["HOME"]) / "Library" / "Application Support"
           / "voice-buddy" / "logs" / "voice-buddy-debug.log")
    text = log.read_text() if log.exists() else ""
    assert secret not in text
