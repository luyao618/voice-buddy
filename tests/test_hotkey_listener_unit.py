"""Unit tests for voice_buddy.hotkey_listener.

Pyobjc is mocked because the runner may not have it installed and we want
to validate Python-side flow control (signal handlers, readiness invariant,
config reload) without needing a real EventTap.
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from unittest import mock

import pytest


@pytest.fixture
def tmp_vb_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "voice_buddy.config.get_config_dir",
        lambda: tmp_path,
    )
    yield tmp_path


def test_check_darwin_raises_on_non_darwin():
    from voice_buddy import hotkey_listener
    with mock.patch.object(sys, "platform", "linux"):
        with pytest.raises(RuntimeError, match="requires macOS"):
            hotkey_listener._check_darwin()


def test_write_readiness_files_creates_pid_and_version(tmp_vb_dir):
    from voice_buddy import coord, hotkey_listener
    import voice_buddy

    hotkey_listener._write_readiness_files()

    assert coord.listener_pid_path().read_text().strip() == str(os.getpid())
    assert coord.listener_version_path().read_text().strip() == voice_buddy.__version__


def test_record_accessibility_error_writes_marker(tmp_vb_dir):
    from voice_buddy import coord, hotkey_listener
    hotkey_listener._record_accessibility_error()
    text = coord.listener_error_path().read_text()
    assert "ACCESSIBILITY_NOT_GRANTED" in text
    assert sys.executable in text


def test_signal_handlers_set_flags():
    from voice_buddy import hotkey_listener
    hotkey_listener._state["config_dirty"] = False

    # SIGHUP handler — should set config_dirty.
    with mock.patch.object(hotkey_listener, "_stop_runloop"):
        hotkey_listener._on_sighup(signal.SIGHUP, None)
    assert hotkey_listener._state["config_dirty"] is True

    # SIGTERM handler — should call _stop_runloop.
    with mock.patch.object(hotkey_listener, "_stop_runloop") as stop:
        hotkey_listener._on_sigterm(signal.SIGTERM, None)
        stop.assert_called_once()


def test_apply_config_reload_disables_tap_when_off(tmp_vb_dir):
    from voice_buddy import hotkey_listener
    from voice_buddy.config import save_user_config, load_user_config

    cfg = load_user_config()
    cfg["hotkey_enabled"] = False
    save_user_config(cfg)

    # Pretend tap is currently installed.
    hotkey_listener._state["tap_ref"] = object()
    hotkey_listener._state["current_keycode"] = 120

    with mock.patch.object(hotkey_listener, "_remove_event_tap") as remove:
        hotkey_listener._apply_config_reload()
        remove.assert_called_once()
    assert hotkey_listener._state["current_keycode"] is None


def test_apply_config_reload_rebinds_when_keycode_changes(tmp_vb_dir):
    from voice_buddy import hotkey_listener
    from voice_buddy.config import save_user_config, load_user_config

    cfg = load_user_config()
    cfg["hotkey"] = "F3"
    cfg["hotkey_enabled"] = True
    save_user_config(cfg)

    hotkey_listener._state["tap_ref"] = object()
    hotkey_listener._state["current_keycode"] = 120  # F2

    with mock.patch.object(hotkey_listener, "_remove_event_tap") as remove, \
         mock.patch.object(hotkey_listener, "_install_event_tap",
                            return_value=(object(), object())) as install:
        hotkey_listener._apply_config_reload()
        remove.assert_called_once()
        install.assert_called_once()
        # Should be called with F3's keycode (99).
        assert install.call_args[0][0] == 99


def test_idle_tick_self_exit_when_no_sessions(tmp_vb_dir):
    from voice_buddy import coord, hotkey_listener

    # No session files exist; idle tick should call _stop_runloop().
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    coord.write_atomic(coord.listener_version_path(), "x")

    with mock.patch.object(hotkey_listener, "_stop_runloop") as stop_mock:
        hotkey_listener._idle_tick()
        stop_mock.assert_called_once()

    # Pidfile and version file should be removed before exit.
    assert not coord.listener_pid_path().exists()
    assert not coord.listener_version_path().exists()


def test_idle_tick_no_exit_when_sessions_present(tmp_vb_dir):
    from voice_buddy import coord, hotkey_listener

    # Touch a session file.
    coord.session_alive_path("test-session").write_text("123")

    # Should NOT exit.
    with mock.patch("os._exit") as exit_mock:
        hotkey_listener._idle_tick()
        exit_mock.assert_not_called()
