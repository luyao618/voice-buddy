"""Tests for the new CLI commands: stop, hotkey config, hotkey-doctor."""

from __future__ import annotations

import json
import re
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

from voice_buddy import cli, hotkey_doctor


@pytest.fixture
def tmp_vb_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "voice_buddy.config.get_config_dir",
        lambda: tmp_path,
    )
    yield tmp_path


def test_do_stop_calls_kill_all(tmp_vb_dir, capsys):
    with mock.patch("voice_buddy.playback_pids.kill_all", return_value=2) as kill_all:
        rc = cli.do_stop()
    assert rc == 0
    kill_all.assert_called_once()
    out = capsys.readouterr().out
    assert "Stopped 2" in out


def test_set_hotkey_valid_writes_config_and_signals(tmp_vb_dir, capsys):
    with mock.patch("voice_buddy.coord.reload_listener_config", return_value=True):
        rc = cli.do_set_hotkey(hotkey="F3")
    assert rc == 0
    from voice_buddy.config import load_user_config
    cfg = load_user_config()
    assert cfg["hotkey"] == "F3"
    out = capsys.readouterr().out
    assert "F3" in out
    assert "listener reloaded" in out


def test_set_hotkey_invalid_returns_error(tmp_vb_dir, capsys):
    rc = cli.do_set_hotkey(hotkey="F99")
    assert rc == 2
    err = capsys.readouterr().err
    assert "Unsupported hotkey" in err


def test_set_hotkey_disable_then_enable(tmp_vb_dir):
    with mock.patch("voice_buddy.coord.reload_listener_config", return_value=False):
        cli.do_set_hotkey(disable=True)
        from voice_buddy.config import load_user_config
        assert load_user_config()["hotkey_enabled"] is False

        cli.do_set_hotkey(enable=True)
        assert load_user_config()["hotkey_enabled"] is True


def test_hotkey_doctor_non_interactive_emits_warn_for_fkey(tmp_vb_dir, capsys):
    rc = cli.do_hotkey_doctor(non_interactive=True, as_json=False)
    out = capsys.readouterr().out
    assert "F-key fn-mode" in out
    if sys.platform == "darwin":
        assert "[WARN]" in out
        assert "skipped" in out
    else:
        assert "[SKIP]" in out
        assert "non-darwin" in out
    # Doctor exits with WARN (1) or FAIL (2) depending on Accessibility — either is fine.
    assert rc in (0, 1, 2)


def test_hotkey_doctor_json_output(tmp_vb_dir, capsys):
    rc = cli.do_hotkey_doctor(non_interactive=True, as_json=True)
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "rows" in data
    assert "version" in data
    assert any(r["check"] == "F-key fn-mode" for r in data["rows"])
    assert rc in (0, 1, 2)


def _fake_quartz(tap):
    return SimpleNamespace(
        kCGEventKeyDown=10,
        kCGSessionEventTap=1,
        kCGHeadInsertEventTap=2,
        kCGEventTapOptionListenOnly=3,
        CGEventTapCreate=mock.Mock(return_value=tap),
    )


def test_accessibility_check_reports_observed_eventtap_success(
        tmp_vb_dir, monkeypatch):
    quartz = _fake_quartz(tap=object())
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "Quartz", quartz)

    row = hotkey_doctor.check_accessibility_granted()

    assert row["status"] == hotkey_doctor.OK
    quartz.CGEventTapCreate.assert_called_once()


def test_accessibility_check_reports_eventtap_creation_failure(
        tmp_vb_dir, monkeypatch):
    quartz = _fake_quartz(tap=None)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "Quartz", quartz)

    row = hotkey_doctor.check_accessibility_granted()

    assert row["status"] == hotkey_doctor.FAIL
    assert "CGEventTapCreate returned NULL" in row["detail"]


def test_accessibility_check_skips_off_darwin(tmp_vb_dir, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")

    row = hotkey_doctor.check_accessibility_granted()

    assert row["status"] == hotkey_doctor.SKIP


def test_doctor_json_and_table_report_the_same_observed_rows(
        tmp_vb_dir, monkeypatch, capsys):
    monkeypatch.setattr(sys, "platform", "linux")

    json_rc = hotkey_doctor.run_doctor(non_interactive=True, as_json=True)
    json_rows = json.loads(capsys.readouterr().out)["rows"]
    table_rc = hotkey_doctor.run_doctor(non_interactive=True, as_json=False)
    table = capsys.readouterr().out

    assert json_rc == table_rc
    assert "EventTap reachability" not in table
    table_rows = []
    for line in table.splitlines():
        match = re.match(r"^\s+\[(\w+)\s*\]\s+(.+?)\s{2,}.*$", line)
        if match:
            table_rows.append((match.group(2), match.group(1)))

    assert table_rows == [
        (row["check"], row["status"]) for row in json_rows
    ]
    fkey = next(row for row in json_rows if row["check"] == "F-key fn-mode")
    assert fkey["status"] == hotkey_doctor.SKIP
