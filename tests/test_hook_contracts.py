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
import io
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

# The complete documented `notification_type` matcher enum. `agent_needs_input`
# and `agent_completed` require Claude Code v2.1.198 or later.
NOTIFICATION_TYPES = [
    "permission_prompt",
    "idle_prompt",
    "auth_success",
    "elicitation_dialog",
    "elicitation_url_dialog",
    "elicitation_complete",
    "elicitation_response",
    "agent_needs_input",
    "agent_completed",
]


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


@pytest.mark.parametrize("ntype", NOTIFICATION_TYPES)
def test_notification_documented_types_all_speak(ntype):
    """Every type in the current official enum still notifies.

    These are the documented `notification_type` matcher values. They are
    listed exhaustively so a schema change shows up here rather than silently
    reducing coverage.
    """
    ctx = analyze_context({**NOTIFICATION, "notification_type": ntype})
    assert ctx is not None and ctx.event == "notification"


def test_notification_type_fixtures_match_documented_enum():
    """Guard the fixture list itself against drift.

    An earlier revision of this file listed `idle_timeout` and
    `waiting_for_input`, neither of which exists in the schema — the
    parametrized test passed anyway, so it looked like enum coverage while
    testing nothing real. Pinning the count and membership makes that failure
    mode visible.
    """
    assert len(NOTIFICATION_TYPES) == 9
    assert "permission_prompt" in NOTIFICATION_TYPES
    assert "agent_completed" in NOTIFICATION_TYPES
    # Values that never existed must not creep back in.
    assert "idle_timeout" not in NOTIFICATION_TYPES
    assert "waiting_for_input" not in NOTIFICATION_TYPES


@pytest.mark.parametrize("ntype", [
    "some_future_type", "", None, 123, {"a": 1},
])
def test_notification_unknown_or_malformed_type_still_speaks(ntype):
    """Forward compatibility, kept separate from documented-enum coverage.

    `notification_type` is informational here — Voice Buddy speaks on every
    notification — so an unrecognized or malformed value must not suppress or
    crash the voice.
    """
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

    SystemExit is expected here: with voice enabled this payload trips the
    documented Stop block (exit 2). Catching it keeps the assertion about log
    contents rather than about whether the developer's own config happens to
    have the voice switched on.
    """
    secret = "SUPERSECRETVALUE_hunter2"
    with caplog.at_level(logging.DEBUG, logger="voice_buddy"):
        try:
            main.handle_hook_event({
                **STOP, "last_assistant_message": f"I fixed the bug: {secret}",
            })
        except SystemExit:
            pass
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


# --- Adversarial log hygiene ------------------------------------------------
# `hook_event_name` is free text on a malformed payload. Treat it as hostile:
# it can carry a transcript path, a prompt, or a credential, and the debug log
# outlives the session.

ADVERSARIAL_EVENT_NAMES = [
    "/Users/victim/.claude/projects/acme/secret-transcript.jsonl",
    "Stop\nUSER PROMPT: my aws key is AKIAIOSFODNN7EXAMPLE",
    "SessionStart; password=hunter2",
    "".join(["A"] * 5000),
    "../../etc/passwd",
    "%s %r %(x)s {0} {}",  # format-string injection into the log call
]


@pytest.mark.parametrize("hostile", ADVERSARIAL_EVENT_NAMES)
def test_raw_event_name_never_reaches_the_log(hostile, caplog, monkeypatch):
    """The raw value must not appear in any log record, at any level.

    Drives `run()`, not `handle_hook_event`: the label is logged in `run()`, so
    calling the inner function would leave the leaking line unexercised and the
    test would pass regardless.
    """
    payload = json.dumps({"hook_event_name": hostile})
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    # Keep run()'s basicConfig from attaching a file handler to the real
    # config dir; caplog still captures the records.
    monkeypatch.setattr(logging, "basicConfig", lambda **kw: None)

    with caplog.at_level(logging.DEBUG, logger="voice_buddy"):
        try:
            main.run()
        except SystemExit:
            pass

    assert hostile not in caplog.text
    # A distinctive fragment must not survive either, so a truncated echo
    # cannot pass by being a prefix of the original.
    for fragment in ("secret-transcript", "AKIAIOSFODNN7EXAMPLE", "hunter2",
                     "etc/passwd"):
        if fragment in hostile:
            assert fragment not in caplog.text


@pytest.mark.parametrize("hostile", ADVERSARIAL_EVENT_NAMES)
def test_safe_event_label_reduces_unknown_names_to_a_fixed_token(hostile):
    label = main.safe_event_label({"hook_event_name": hostile})
    assert hostile not in label
    assert label.startswith("unknown")


@pytest.mark.parametrize("name", ["SessionStart", "SessionEnd", "Notification", "Stop"])
def test_safe_event_label_passes_through_allowlisted_names(name):
    """Known event names stay legible; only unrecognized values are reduced."""
    assert main.safe_event_label({"hook_event_name": name}) == name


def test_safe_event_label_describes_shape_without_echoing_values():
    assert main.safe_event_label([1, 2, 3]).startswith("unknown(non-object")
    assert main.safe_event_label({"hook_event_name": None}) == "unknown(absent)"
    assert main.safe_event_label({"hook_event_name": 42}) == "unknown(int)"
    # A secret in a *value* of a non-object payload must not surface either.
    assert "hunter2" not in main.safe_event_label(["hunter2"])


def test_sensitive_payload_fields_never_reach_the_log(caplog):
    """Transcript path, prompt text and message body are all off-limits."""
    secrets = {
        "transcript_path": "/Users/victim/.claude/projects/SECRET_PATH.jsonl",
        "last_assistant_message": "SECRET_MESSAGE hunter2",
        "message": "SECRET_NOTIFICATION hunter2",
        "cwd": "/Users/victim/SECRET_CWD",
    }
    with caplog.at_level(logging.DEBUG, logger="voice_buddy"):
        for event in ("Stop", "Notification", "SessionStart", "SessionEnd"):
            try:
                main.handle_hook_event({"hook_event_name": event, **secrets})
            except SystemExit:
                pass
    for value in secrets.values():
        assert value not in caplog.text
