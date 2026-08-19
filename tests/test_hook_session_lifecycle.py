# tests/test_hook_session_lifecycle.py
"""Hook-level session lifecycle contract tests (YAO-340).

`test_session_lifecycle.py` calls the supervisor helpers directly, and
`test_hook_contracts.py` only asserts that a SessionStart/SessionEnd payload is
recognized as an event. Neither proves the piece in between: that the real hook
wiring in `main.handle_hook_event` hands the payload's own `session_id` to
`ensure_listener_for_session()` / `release_session()`.

That gap is what these tests close, at two levels:

  1. Wiring — the supervisor is called once, with the *original* session id
     from the payload, for every documented `source` (including `resume`) and
     every documented SessionEnd `reason`.
  2. State — two concurrently live sessions, where ending one must leave the
     other's alive file intact. This is the behavior that actually matters:
     the listener is a singleton shared by every session, so a SessionEnd that
     released more than its own session would tear the hotkey out from under a
     session that is still running.

The state tests pin `sys.platform` to "darwin" so they are deterministic on
any host: the supervisor is macOS-gated, and without pinning, the concurrent
assertions would silently no-op into vacuous passes off macOS.
"""
from __future__ import annotations

import sys
from unittest import mock

import pytest

from voice_buddy import main


COMMON = {
    "transcript_path": "/Users/u/.claude/projects/p/session.jsonl",
    "cwd": "/Users/u/project",
    "permission_mode": "default",
}

# Documented SessionStart sources and SessionEnd reasons.
SOURCES = ["startup", "resume", "clear", "compact", "fork"]
REASONS = ["clear", "logout", "prompt_input_exit", "other"]


@pytest.fixture
def vb_dir(tmp_path, monkeypatch):
    """Point voice-buddy state at a tmp dir; keep the run silent and offline."""
    monkeypatch.setattr("voice_buddy.config.get_config_dir", lambda: tmp_path)
    # The lifecycle is what's under test — not audio. Keep both output paths
    # inert so these tests never touch the network or a real audio device.
    monkeypatch.setattr(main, "play_audio", lambda *a, **k: True)
    monkeypatch.setattr(main, "synthesize_to_file", lambda *a, **k: None)
    monkeypatch.setattr(main, "resolve_audio_path", lambda *a, **k: None)
    return tmp_path


@pytest.fixture
def darwin(monkeypatch):
    """Pin the platform so the macOS-gated supervisor actually runs."""
    monkeypatch.setattr(sys, "platform", "darwin")


# --- 1. Wiring: the payload's own session_id reaches the supervisor ---------

@pytest.mark.parametrize("source", SOURCES)
def test_sessionstart_passes_original_session_id_to_supervisor(source, vb_dir):
    """Every documented source, including `resume`, must wire the id through.

    Asserted against the exact id from the payload: a regression that dropped
    the field and fell back to the "default" placeholder would still call the
    supervisor, so asserting "was called" alone would not catch it.
    """
    session_id = f"sess-{source}-9f8e7d"
    with mock.patch(
        "voice_buddy.listener_supervisor.ensure_listener_for_session"
    ) as ensure:
        main.handle_hook_event({
            **COMMON, "hook_event_name": "SessionStart",
            "source": source, "session_id": session_id,
        })
    ensure.assert_called_once_with(session_id)


@pytest.mark.parametrize("reason", REASONS)
def test_sessionend_passes_original_session_id_to_supervisor(reason, vb_dir):
    session_id = f"sess-{reason}-1a2b3c"
    with mock.patch(
        "voice_buddy.listener_supervisor.release_session"
    ) as release:
        main.handle_hook_event({
            **COMMON, "hook_event_name": "SessionEnd",
            "reason": reason, "session_id": session_id,
        })
    release.assert_called_once_with(session_id)


def test_sessionstart_does_not_release_and_sessionend_does_not_ensure(vb_dir):
    """The two lifecycle edges must not cross-fire.

    A SessionStart that also released, or a SessionEnd that also ensured,
    would corrupt the shared alive-file set without failing any single-edge
    assertion above.
    """
    with mock.patch(
        "voice_buddy.listener_supervisor.ensure_listener_for_session"
    ) as ensure, mock.patch(
        "voice_buddy.listener_supervisor.release_session"
    ) as release:
        main.handle_hook_event({
            **COMMON, "hook_event_name": "SessionStart",
            "source": "resume", "session_id": "sid-start"})
        assert ensure.call_count == 1
        assert release.call_count == 0

        main.handle_hook_event({
            **COMMON, "hook_event_name": "SessionEnd",
            "reason": "other", "session_id": "sid-end"})
        assert ensure.call_count == 1
        assert release.call_count == 1


def test_session_id_is_not_mangled_when_unusual(vb_dir):
    """The raw value is forwarded as-is; sanitizing is the supervisor's job.

    Guards the boundary: `main` must not quietly rewrite the id, because the
    supervisor derives the alive-file name from it and a rewrite here would
    desynchronize start from end.
    """
    for session_id in ("UPPER-Case_123", "a" * 120, "sess.with.dots"):
        with mock.patch(
            "voice_buddy.listener_supervisor.ensure_listener_for_session"
        ) as ensure:
            main.handle_hook_event({
                **COMMON, "hook_event_name": "SessionStart",
                "source": "startup", "session_id": session_id})
        ensure.assert_called_once_with(session_id)


def test_missing_session_id_falls_back_without_crashing(vb_dir):
    """An absent id must degrade to the documented placeholder, not raise."""
    with mock.patch(
        "voice_buddy.listener_supervisor.ensure_listener_for_session"
    ) as ensure:
        main.handle_hook_event({**COMMON, "hook_event_name": "SessionStart",
                                "source": "startup"})
    ensure.assert_called_once_with("default")


def test_supervisor_failure_never_breaks_the_session(vb_dir):
    """A supervisor blow-up must stay contained.

    The hotkey is a convenience; a failure here must not propagate out of the
    hook, because Claude Code reports a non-zero exit as a hook failure.
    """
    with mock.patch(
        "voice_buddy.listener_supervisor.ensure_listener_for_session",
        side_effect=RuntimeError("supervisor exploded"),
    ):
        main.handle_hook_event({**COMMON, "hook_event_name": "SessionStart",
                                "source": "startup", "session_id": "sid-boom"})

    with mock.patch(
        "voice_buddy.listener_supervisor.release_session",
        side_effect=RuntimeError("supervisor exploded"),
    ):
        main.handle_hook_event({**COMMON, "hook_event_name": "SessionEnd",
                                "reason": "other", "session_id": "sid-boom"})


# --- 2. State: concurrent sessions, observed through the real supervisor ----

def _start(session_id):
    main.handle_hook_event({**COMMON, "hook_event_name": "SessionStart",
                            "source": "startup", "session_id": session_id})


def _end(session_id, reason="other"):
    main.handle_hook_event({**COMMON, "hook_event_name": "SessionEnd",
                            "reason": reason, "session_id": session_id})


def _alive(session_id):
    from voice_buddy import coord
    return coord.session_alive_path(session_id).exists()


@pytest.fixture
def no_spawn():
    """Run the real supervisor logic, minus spawning an actual listener."""
    from voice_buddy import listener_supervisor
    with mock.patch.object(listener_supervisor, "_spawn_detached_listener"):
        yield


def test_two_sessions_start_start_end_leaves_the_other_alive(
        vb_dir, darwin, no_spawn):
    """start(A), start(B), end(A) → B survives.

    The listener is a singleton shared across sessions, so releasing one
    session must be scoped to that session's own alive file.
    """
    _start("sess-aaa-111")
    _start("sess-bbb-222")
    assert _alive("sess-aaa-111") and _alive("sess-bbb-222")

    _end("sess-aaa-111")

    assert not _alive("sess-aaa-111"), "ended session should be released"
    assert _alive("sess-bbb-222"), "concurrent session must survive"


def test_ending_the_second_session_releases_only_it(vb_dir, darwin, no_spawn):
    """Mirror of the above, ending B instead of A — order must not matter."""
    _start("sess-aaa-111")
    _start("sess-bbb-222")

    _end("sess-bbb-222")

    assert _alive("sess-aaa-111")
    assert not _alive("sess-bbb-222")


def test_all_sessions_released_only_after_each_ends(vb_dir, darwin, no_spawn):
    """Three concurrent sessions drain one at a time, never in bulk."""
    ids = ["sess-a-1", "sess-b-2", "sess-c-3"]
    for sid in ids:
        _start(sid)
    assert all(_alive(s) for s in ids)

    remaining = list(ids)
    for sid in ids:
        _end(sid)
        remaining.remove(sid)
        assert not _alive(sid)
        assert all(_alive(r) for r in remaining), (
            f"ending {sid} disturbed still-live sessions {remaining}")


def test_resume_reuses_the_same_session_id_slot(vb_dir, darwin, no_spawn):
    """A resumed session re-registers under its own id, not a new one.

    `source=resume` carries the id of the session being resumed, so the alive
    file must be that same id — otherwise a resume would leak a stale entry
    and the matching SessionEnd would release the wrong slot.
    """
    sid = "sess-resume-777"
    _start(sid)
    assert _alive(sid)

    main.handle_hook_event({**COMMON, "hook_event_name": "SessionStart",
                            "source": "resume", "session_id": sid})
    from voice_buddy import coord
    alive_files = list(coord.sessions_dir().glob("*.alive"))
    assert len(alive_files) == 1, f"resume leaked extra files: {alive_files}"

    _end(sid)
    assert not _alive(sid)


def test_sessionend_for_unknown_session_leaves_live_sessions_untouched(
        vb_dir, darwin, no_spawn):
    """An end for a session we never saw is a no-op, not a purge."""
    _start("sess-live-1")
    _end("sess-never-started")
    assert _alive("sess-live-1")


def test_duplicate_sessionend_is_idempotent(vb_dir, darwin, no_spawn):
    """Claude Code may deliver SessionEnd more than once; the second is inert."""
    _start("sess-a-1")
    _start("sess-b-2")
    _end("sess-a-1")
    _end("sess-a-1")
    assert not _alive("sess-a-1")
    assert _alive("sess-b-2")
