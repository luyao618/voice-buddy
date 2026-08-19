# tests/test_hook_contracts.py
"""Contract tests for Claude Code hook payloads (YAO-340).

These fixtures are transcribed from the documented 2.1.x hook input schemas for
the four events Voice Buddy registers: SessionStart, SessionEnd, Notification,
and Stop.

The governing rule for every case here: a hook must never fail the user's
session. Claude Code treats a non-zero exit as a hook failure and surfaces it,
so a payload this plugin does not understand has to degrade quietly rather than
raise. The one deliberate exception is Stop's documented exit-2 block, which is
how the synchronous decision contract is expressed.
"""
import json
import logging

import pytest

from voice_buddy import injector, main
from voice_buddy.context import analyze_context, coerce_text


# --- Documented payloads ----------------------------------------------------
# Common fields per the "Common input fields" table; event-specific fields per
# each event's own input section.

COMMON = {
    "session_id": "abc123",
    "transcript_path": "/Users/u/.claude/projects/p/session.jsonl",
    "cwd": "/Users/u/project",
    "permission_mode": "default",
}

SESSION_START = {**COMMON, "hook_event_name": "SessionStart",
                 "source": "startup", "model": "claude-sonnet-5"}
SESSION_END = {**COMMON, "hook_event_name": "SessionEnd", "reason": "other"}
NOTIFICATION = {**COMMON, "hook_event_name": "Notification",
                "message": "Claude needs your permission",
                "title": "Permission needed",
                "notification_type": "permission_prompt"}
STOP = {**COMMON, "hook_event_name": "Stop", "stop_hook_active": False,
        "last_assistant_message": "I fixed the bug and updated the tests.",
        "background_tasks": [], "session_crons": []}


# --- Valid payloads ---------------------------------------------------------

def test_sessionstart_payload_is_recognized():
    ctx = analyze_context(SESSION_START)
    assert ctx is not None and ctx.event == "sessionstart"


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "compact", "fork"])
def test_sessionstart_all_documented_sources(source):
    """Every documented `source` still produces the session-start voice.

    Voice Buddy greets on any session start; the field is enumerated here so a
    future source value can't silently change behavior.
    """
    ctx = analyze_context({**SESSION_START, "source": source})
    assert ctx is not None and ctx.event == "sessionstart"


def test_sessionstart_without_optional_model():
    # `model` can be omitted, e.g. after /clear or conversation recovery.
    payload = {k: v for k, v in SESSION_START.items() if k != "model"}
    assert analyze_context(payload).event == "sessionstart"


@pytest.mark.parametrize("reason", ["clear", "logout", "prompt_input_exit", "other"])
def test_sessionend_all_documented_reasons(reason):
    ctx = analyze_context({**SESSION_END, "reason": reason})
    assert ctx is not None and ctx.event == "sessionend"


def test_notification_uses_message_text():
    ctx = analyze_context(NOTIFICATION)
    assert ctx.event == "notification"
    assert ctx.detail == "Claude needs your permission"


def test_notification_falls_back_to_title():
    ctx = analyze_context({**NOTIFICATION, "message": ""})
    assert ctx.detail == "Permission needed"


@pytest.mark.parametrize("ntype", [
    "permission_prompt", "idle_timeout", "waiting_for_input", "some_future_type",
])
def test_notification_variants_all_speak(ntype):
    """notification_type is informational; every variant still notifies."""
    ctx = analyze_context({**NOTIFICATION, "notification_type": ntype})
    assert ctx is not None and ctx.event == "notification"


def test_notification_detail_is_capped():
    ctx = analyze_context({**NOTIFICATION, "message": "x" * 5000})
    assert len(ctx.detail) <= 200


# --- Missing / malformed / unknown ------------------------------------------

@pytest.mark.parametrize("payload", [
    {},
    {"hook_event_name": None},
    {"hook_event_name": 42},
    {"hook_event_name": ""},
    {"hook_event_name": "PreToolUse"},      # event we don't register
    {"hook_event_name": "SubagentStop"},    # adjacent event, must stay silent
])
def test_unknown_or_malformed_events_are_silent(payload):
    assert analyze_context(payload) is None


@pytest.mark.parametrize("payload", [None, [], [1, 2, 3], "string", 42])
def test_non_dict_payload_is_ignored(payload):
    """A non-object payload must not raise; it previously crashed with
    AttributeError and exited 1, which Claude Code reports as a hook failure."""
    assert analyze_context(payload) is None


@pytest.mark.parametrize("bad", [123, {"a": 1}, True, None])
def test_notification_with_non_string_message_degrades(bad):
    """Previously raised TypeError/KeyError on slicing a non-string."""
    ctx = analyze_context({**NOTIFICATION, "message": bad, "title": ""})
    assert ctx is not None and ctx.event == "notification"
    assert isinstance(ctx.detail, str)


def test_coerce_text_handles_content_blocks():
    assert coerce_text([{"type": "text", "text": "hello"}]) == "hello"
    assert coerce_text("plain") == "plain"
    assert coerce_text(123) == ""
    assert coerce_text(None) == ""


# --- Stop: synchronous decision contract ------------------------------------

def _run_stop(payload, cfg=None):
    """Return the exit code the Stop hook would produce (0 = allow stop)."""
    cfg = cfg or {"style": "cute-girl", "nickname": "Master"}
    try:
        injector.process_stop_event(payload, cfg)
    except SystemExit as e:
        return e.code
    return 0


def test_stop_blocks_with_exit_2_on_completion():
    """The documented block: exit 2, with the reason on stderr."""
    assert _run_stop(STOP) == 2


def test_stop_allows_when_no_completion_signal():
    assert _run_stop({**STOP, "last_assistant_message": "What would you like next?"}) == 0


def test_stop_hook_active_true_prevents_recursion():
    """The documented loop guard: never block when already continuing."""
    assert _run_stop({**STOP, "stop_hook_active": True}) == 0


@pytest.mark.parametrize("active,blocks", [
    (True, False),      # documented active -> must not block
    ("true", False),    # string spelling of true
    (1, False),
    (False, True),      # documented inactive -> may block
    ("false", True),    # truthy in Python, but means NOT active
    (None, True),       # absent-ish
    (0, True),
    ("", True),
])
def test_stop_hook_active_is_compared_against_true(active, blocks):
    """Raw truthiness is wrong in both directions.

    The string "false" is truthy in Python: reading it as "active" would
    silently disable the voice on every turn. Conversely 0/""/None are falsy
    but are not the documented `true`, so they must not suppress the block.
    """
    assert (_run_stop({**STOP, "stop_hook_active": active}) == 2) is blocks


def test_stop_cannot_recurse_indefinitely():
    """Simulate the retry chain: once Claude Code flags the hook as active,
    every subsequent invocation allows the stop, so the chain terminates."""
    codes = [_run_stop({**STOP, "stop_hook_active": i > 0}) for i in range(5)]
    assert codes[0] == 2
    assert all(c == 0 for c in codes[1:]), "hook re-blocked while already active"


@pytest.mark.parametrize("bad", [123, {"text": "done"}, True])
def test_stop_with_non_string_message_does_not_crash(bad):
    """Previously raised TypeError out of the regex, which the entry point
    swallowed into a silent success."""
    assert _run_stop({**STOP, "last_assistant_message": bad,
                      "transcript_path": ""}) == 0


def test_stop_prefers_last_assistant_message_over_transcript(tmp_path):
    """The docs recommend last_assistant_message because the transcript file
    lags. A stale transcript must not override the field."""
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps({
        "type": "assistant",
        "message": {"role": "assistant", "content": "stale, no keyword here"},
    }) + "\n")
    payload = {**STOP, "last_assistant_message": "I fixed the bug",
               "transcript_path": str(transcript)}
    assert _run_stop(payload) == 2


def test_stop_falls_back_to_transcript_when_field_absent(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps({
        "type": "assistant",
        "message": {"role": "assistant", "content": "I fixed the bug"},
    }) + "\n")
    payload = {k: v for k, v in STOP.items() if k != "last_assistant_message"}
    assert _run_stop({**payload, "transcript_path": str(transcript)}) == 2


def test_stop_with_missing_transcript_is_silent():
    payload = {k: v for k, v in STOP.items() if k != "last_assistant_message"}
    assert _run_stop({**payload, "transcript_path": "/no/such/file.jsonl"}) == 0


@pytest.mark.parametrize("bad_path", [None, 123, "", []])
def test_stop_with_unusable_transcript_path_is_silent(bad_path):
    payload = {k: v for k, v in STOP.items() if k != "last_assistant_message"}
    assert _run_stop({**payload, "transcript_path": bad_path}) == 0


def test_stop_tolerates_background_tasks_and_crons():
    """v2.1.145+ adds these arrays; their presence must not change behavior."""
    payload = {**STOP, "background_tasks": [
        {"id": "t1", "type": "shell", "status": "running",
         "description": "tail logs", "command": "tail -f /var/log/syslog"},
    ], "session_crons": [
        {"id": "c1", "schedule": "0 9 * * 1-5", "recurring": True,
         "prompt": "check the build"},
    ]}
    assert _run_stop(payload) == 2


def test_stop_on_non_dict_payload_is_silent():
    for payload in (None, [], "str", 42):
        assert _run_stop(payload) == 0


# --- Log hygiene ------------------------------------------------------------

def test_logs_do_not_leak_transcript_or_message_content(caplog):
    """Debug logs must not carry conversation text.

    The hook sees the assistant's final message, which can contain anything the
    user was working on. It is written to a long-lived file, so the event name
    is loggable but the content is not.
    """
    secret = "SUPERSECRETVALUE_hunter2"
    with caplog.at_level(logging.DEBUG, logger="voice_buddy"):
        main.handle_hook_event({
            **STOP, "last_assistant_message": f"I fixed the bug: {secret}",
        })
    assert secret not in caplog.text


def test_logs_do_not_leak_notification_message(caplog):
    secret = "SUPERSECRETVALUE_notify"
    with caplog.at_level(logging.DEBUG, logger="voice_buddy"):
        try:
            main.handle_hook_event({**NOTIFICATION, "message": secret})
        except SystemExit:
            pass
    assert secret not in caplog.text


def test_malformed_payload_is_logged_as_a_warning(caplog):
    """A payload we can't process must leave a trace.

    It previously produced no log line at all beyond the event name, so a real
    incompatibility was indistinguishable from "nothing to say".
    """
    with caplog.at_level(logging.DEBUG, logger="voice_buddy"):
        main.handle_hook_event([1, 2, 3])
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


def test_non_string_event_name_is_logged_as_a_warning(caplog):
    with caplog.at_level(logging.DEBUG, logger="voice_buddy"):
        main.handle_hook_event({"hook_event_name": 42})
    assert any(r.levelno >= logging.WARNING for r in caplog.records)
