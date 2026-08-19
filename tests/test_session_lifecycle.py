"""Tests for SessionStart/SessionEnd hotkey supervisor wiring."""

from __future__ import annotations

import os
import sys
from unittest import mock

import pytest


@pytest.fixture
def tmp_vb_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "voice_buddy.config.get_config_dir",
        lambda: tmp_path,
    )
    yield tmp_path


def test_session_end_unlinks_alive_file(tmp_vb_dir):
    from voice_buddy import coord, listener_supervisor

    sid = "test-sid"
    alive = coord.session_alive_path(sid)
    alive.write_text("123")
    assert alive.exists()

    result = listener_supervisor.release_session(sid)
    if sys.platform != "darwin":
        assert result is None
        # On non-darwin, release_session is a no-op (does NOT unlink).
        return
    assert result is True
    assert not alive.exists()


def test_release_session_idempotent_on_missing_file(tmp_vb_dir):
    from voice_buddy import listener_supervisor
    if sys.platform != "darwin":
        assert listener_supervisor.release_session("nope") is None
        return
    assert listener_supervisor.release_session("never-existed") is True


def test_ensure_listener_skipped_on_non_darwin(tmp_vb_dir, monkeypatch):
    from voice_buddy import listener_supervisor
    monkeypatch.setattr(sys, "platform", "linux")
    assert listener_supervisor.ensure_listener_for_session("sid") is None


def test_ensure_listener_skipped_when_disabled(tmp_vb_dir, monkeypatch):
    from voice_buddy import listener_supervisor
    from voice_buddy.config import load_user_config, save_user_config

    monkeypatch.setattr(sys, "platform", "darwin")
    cfg = load_user_config()
    cfg["hotkey_enabled"] = False
    save_user_config(cfg)

    assert listener_supervisor.ensure_listener_for_session("sid") is None


def test_ensure_listener_attaches_when_already_alive(tmp_vb_dir, monkeypatch):
    from voice_buddy import coord, listener_supervisor
    import voice_buddy

    monkeypatch.setattr(sys, "platform", "darwin")

    # Pretend a live listener with matching version exists. The pytest process
    # stands in for it, so the ownership probe is stubbed — see test_coord.py
    # for the tests that cover ownership itself.
    monkeypatch.setattr(coord, "_process_is_listener", lambda pid: True)
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    coord.write_atomic(coord.listener_version_path(), voice_buddy.__version__)

    with mock.patch.object(listener_supervisor, "_spawn_detached_listener") as spawn:
        result = listener_supervisor.ensure_listener_for_session("sid-attach")
    assert result is True
    spawn.assert_not_called()
    # Session alive file written.
    assert coord.session_alive_path("sid-attach").exists()


def test_ensure_listener_spawns_when_no_listener(tmp_vb_dir, monkeypatch):
    from voice_buddy import coord, listener_supervisor
    monkeypatch.setattr(sys, "platform", "darwin")

    # Make absolutely sure no stale pidfile is leftover from a sibling test.
    coord.cleanup_stale_listener_artifacts()

    with mock.patch.object(listener_supervisor, "_spawn_detached_listener") as spawn:
        # listener_alive() will return False (no pidfile).
        result = listener_supervisor.ensure_listener_for_session("sid-spawn")
    spawn.assert_called_once()
    # Result is False because the mocked spawn never wrote a pidfile, so
    # readiness poll times out — that's the documented AC11 behavior.
    assert result is False
    assert coord.session_alive_path("sid-spawn").exists()
