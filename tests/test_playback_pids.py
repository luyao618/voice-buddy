"""Tests for voice_buddy.playback_pids — PID set with concurrent-safe ops."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from unittest import mock

import pytest

from voice_buddy import coord, playback_pids


@pytest.fixture
def tmp_vb_dir(tmp_path, monkeypatch):
    """Redirect VB_DIR to a tmp path so tests don't touch user state."""
    monkeypatch.setattr(
        "voice_buddy.config.get_config_dir",
        lambda: tmp_path,
    )
    yield tmp_path


def _spawn_long_sleeper() -> subprocess.Popen:
    """Spawn a child that lives long enough to be signaled."""
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_add_appends_pid_and_snapshot_returns_live(tmp_vb_dir):
    proc = _spawn_long_sleeper()
    try:
        playback_pids.add(proc.pid)
        live = playback_pids.snapshot()
        assert proc.pid in live
    finally:
        proc.terminate()
        proc.wait(timeout=2)


def test_snapshot_filters_dead_pids(tmp_vb_dir):
    (tmp_vb_dir / "playback_pids").write_text(
        "999999\t999999@old-start-time\n"
    )
    live = playback_pids.snapshot()
    assert 999_999 not in live


def test_kill_all_signals_live_pids_and_truncates(tmp_vb_dir):
    proc1 = _spawn_long_sleeper()
    proc2 = _spawn_long_sleeper()
    try:
        playback_pids.add(proc1.pid)
        playback_pids.add(proc2.pid)
        with mock.patch.object(coord, "process_identity",
                               return_value="999998@old-start-time"):
            playback_pids.add(999_998)

        killed = playback_pids.kill_all(signal.SIGTERM)
        assert killed >= 2  # both live; dead PID skipped

        # Wait for children to actually exit.
        proc1.wait(timeout=2)
        proc2.wait(timeout=2)

        # File truncated.
        pids_file = tmp_vb_dir / "playback_pids"
        assert pids_file.read_text() == ""
    finally:
        for p in (proc1, proc2):
            if p.poll() is None:
                p.kill()
                p.wait(timeout=2)


def test_concurrent_add_does_not_corrupt(tmp_vb_dir):
    """Many concurrent add() calls must all land in the file."""
    pids = list(range(10_000, 10_050))

    def writer(pid):
        playback_pids.add(pid)

    with mock.patch.object(
        coord, "process_identity", side_effect=lambda pid: f"{pid}@start"
    ):
        threads = [threading.Thread(target=writer, args=(p,)) for p in pids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    text = (tmp_vb_dir / "playback_pids").read_text()
    written = sorted(int(x.split("\t", 1)[0]) for x in text.splitlines())
    assert written == sorted(pids)


def test_compact_keeps_only_live_pids(tmp_vb_dir):
    proc = _spawn_long_sleeper()
    try:
        playback_pids.add(proc.pid)
        with mock.patch.object(
            coord, "process_identity",
            side_effect=lambda pid: f"{pid}@old-start-time",
        ):
            for stale in (999_001, 999_002, 999_003):
                playback_pids.add(stale)

        kept = playback_pids.compact()
        assert kept == 1

        text = (tmp_vb_dir / "playback_pids").read_text().strip()
        assert text.startswith(f"{proc.pid}\t{proc.pid}@")
    finally:
        proc.terminate()
        proc.wait(timeout=2)


def test_remove_is_noop(tmp_vb_dir):
    """remove() is documented as a no-op; snapshot filter handles natural exit."""
    playback_pids.remove(12345)  # must not raise
    # File should not even be created by remove().
    assert not (tmp_vb_dir / "playback_pids").exists()


def test_kill_all_with_no_pids_returns_zero(tmp_vb_dir):
    assert playback_pids.kill_all() == 0


def test_needs_compaction_threshold(tmp_vb_dir):
    with mock.patch.object(
        coord, "process_identity", side_effect=lambda pid: f"{pid}@start"
    ):
        for i in range(70):
            playback_pids.add(900_000 + i)
    assert playback_pids.needs_compaction(line_threshold=64) is True
    assert playback_pids.needs_compaction(line_threshold=100) is False


def test_legacy_bare_pid_is_never_signaled(tmp_vb_dir):
    (tmp_vb_dir / "playback_pids").write_text(f"{os.getpid()}\n")
    with mock.patch.object(playback_pids.os, "kill") as kill:
        assert playback_pids.kill_all() == 0
    kill.assert_not_called()
    assert (tmp_vb_dir / "playback_pids").read_text() == ""


@pytest.mark.parametrize("current_identity", [None, "4242@new-start-time"])
def test_unknown_or_recycled_identity_is_never_signaled(
        tmp_vb_dir, current_identity):
    (tmp_vb_dir / "playback_pids").write_text("4242\t4242@old-start-time\n")
    with mock.patch.object(coord, "_process_alive", return_value=True), \
         mock.patch.object(coord, "process_identity",
                           return_value=current_identity), \
         mock.patch.object(playback_pids.os, "kill") as kill:
        assert playback_pids.kill_all() == 0
    kill.assert_not_called()


def test_zombie_identity_is_never_signaled(tmp_vb_dir):
    (tmp_vb_dir / "playback_pids").write_text("4242\t4242@start\n")
    with mock.patch.object(coord, "_process_alive", return_value=False), \
         mock.patch.object(coord, "process_identity",
                           return_value="4242@start"), \
         mock.patch.object(playback_pids.os, "kill") as kill:
        assert playback_pids.kill_all() == 0
    kill.assert_not_called()


def test_signal_error_keeps_registration_for_retry(tmp_vb_dir):
    entry = "4242\t4242@start\n"
    (tmp_vb_dir / "playback_pids").write_text(entry)
    with mock.patch.object(coord, "_process_alive", return_value=True), \
         mock.patch.object(coord, "process_identity",
                           return_value="4242@start"), \
         mock.patch.object(playback_pids.os, "kill",
                           side_effect=PermissionError):
        assert playback_pids.kill_all() == 0
    assert (tmp_vb_dir / "playback_pids").read_text() == entry


@pytest.mark.parametrize("operation", ["kill_all", "compact"])
def test_registry_read_error_does_not_erase_unprocessed_entries(
        tmp_vb_dir, monkeypatch, operation):
    entry = "4242\t4242@start\n"
    path = tmp_vb_dir / "playback_pids"
    path.write_text(entry)
    monkeypatch.setattr(
        playback_pids, "_read_entries",
        mock.Mock(side_effect=PermissionError("temporarily unreadable")),
    )

    with pytest.raises(PermissionError, match="temporarily unreadable"):
        getattr(playback_pids, operation)()

    assert path.read_text() == entry


@pytest.mark.parametrize("operation", ["kill_all", "compact"])
def test_add_during_registry_rewrite_is_preserved(
        tmp_vb_dir, monkeypatch, operation):
    """An add invoked while a rewrite holds the lock runs after the rewrite."""
    entered_read = threading.Event()
    continue_read = threading.Event()
    original_read = playback_pids._read_entries

    def paused_read():
        entered_read.set()
        assert continue_read.wait(timeout=2)
        return original_read()

    monkeypatch.setattr(playback_pids, "_read_entries", paused_read)
    monkeypatch.setattr(coord, "process_identity",
                        lambda pid: f"{pid}@start")
    monkeypatch.setattr(coord, "_process_alive", lambda pid: True)

    rewrite = threading.Thread(target=getattr(playback_pids, operation))
    rewrite.start()
    assert entered_read.wait(timeout=2)

    add_done = threading.Event()
    add_entered_lock = threading.Event()
    original_lock_enter = playback_pids._LockCtx.__enter__

    def observed_lock_enter(lock):
        if threading.current_thread().name == "concurrent-adder":
            add_entered_lock.set()
        return original_lock_enter(lock)

    monkeypatch.setattr(
        playback_pids._LockCtx, "__enter__", observed_lock_enter
    )

    def add_during_rewrite():
        playback_pids.add(222)
        add_done.set()

    adder = threading.Thread(
        target=add_during_rewrite, name="concurrent-adder"
    )
    with mock.patch.object(playback_pids.os, "kill") as kill:
        adder.start()
        assert add_entered_lock.wait(timeout=2)
        assert not add_done.is_set(), "add must block behind the rewrite lock"
        continue_read.set()
        rewrite.join(timeout=2)
        adder.join(timeout=2)

    assert not rewrite.is_alive()
    assert add_done.is_set()
    kill.assert_not_called()
    assert "222\t222@start" in (tmp_vb_dir / "playback_pids").read_text()
