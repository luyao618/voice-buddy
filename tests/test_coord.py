"""Tests for voice_buddy.coord — coord.lock + listener_alive() helpers."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import voice_buddy
from voice_buddy import coord


@pytest.fixture
def tmp_vb_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "voice_buddy.config.get_config_dir",
        lambda: tmp_path,
    )
    yield tmp_path


@pytest.fixture
def owned_pid(monkeypatch):
    """Treat any live PID as our listener.

    Tests use the pytest process as a stand-in listener because it is reliably
    alive, but its command line is not `voice_buddy.hotkey_listener`, so the
    real ownership probe rejects it. Stubbing the probe keeps these tests about
    liveness and version handshake; ownership has its own tests below.
    """
    monkeypatch.setattr(coord, "_process_is_listener", lambda pid: True)


def test_listener_alive_false_when_pidfile_missing(tmp_vb_dir):
    assert coord.listener_alive() is False


def test_listener_alive_false_when_pid_dead(tmp_vb_dir):
    coord.write_atomic(coord.listener_pid_path(), "999999")
    coord.write_atomic(coord.listener_version_path(), voice_buddy.__version__)
    assert coord.listener_alive() is False


def test_listener_alive_false_on_version_drift(tmp_vb_dir, owned_pid):
    # Use our own PID — guaranteed alive — and claim ownership, since the
    # pytest process is not literally `voice_buddy.hotkey_listener`.
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    coord.write_atomic(coord.listener_version_path(), "0.0.0-old")
    assert coord.listener_alive(version_check=True) is False
    # But without version check, it's alive.
    assert coord.listener_alive(version_check=False) is True


def test_listener_alive_true_when_pid_live_and_version_matches(tmp_vb_dir, owned_pid):
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    coord.write_atomic(coord.listener_version_path(), voice_buddy.__version__)
    assert coord.listener_alive() is True


def test_cleanup_stale_listener_artifacts(tmp_vb_dir):
    coord.write_atomic(coord.listener_pid_path(), "12345")
    coord.write_atomic(coord.listener_version_path(), "x")
    coord.write_atomic(coord.listener_error_path(), "err")

    coord.cleanup_stale_listener_artifacts()

    assert not coord.listener_pid_path().exists()
    assert not coord.listener_version_path().exists()
    assert not coord.listener_error_path().exists()
    # Idempotent — second call must not raise.
    coord.cleanup_stale_listener_artifacts()


def test_coord_lock_is_exclusive(tmp_vb_dir):
    """Two fds cannot hold coord.lock LOCK_EX simultaneously."""
    import fcntl
    # First holder takes the lock.
    lock_path = coord.coord_lock_path()
    fd1 = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    fcntl.flock(fd1, fcntl.LOCK_EX)
    try:
        # Non-blocking acquire from a different fd must fail.
        with pytest.raises((BlockingIOError, OSError)):
            with coord.coord_lock(blocking=False):
                pass
    finally:
        fcntl.flock(fd1, fcntl.LOCK_UN)
        os.close(fd1)

    # After release, acquire should succeed.
    with coord.coord_lock(blocking=False):
        pass


def test_coord_lock_serializes_sequentially(tmp_vb_dir):
    """Sequential coord_lock acquires both succeed (no leak)."""
    with coord.coord_lock():
        pass
    with coord.coord_lock():
        pass


def test_write_atomic_creates_file_with_content(tmp_vb_dir):
    target = tmp_vb_dir / "atomic_test.txt"
    coord.write_atomic(target, "hello")
    assert target.read_text() == "hello"


def test_write_atomic_overwrites(tmp_vb_dir):
    target = tmp_vb_dir / "atomic_test.txt"
    coord.write_atomic(target, "first")
    coord.write_atomic(target, "second")
    assert target.read_text() == "second"


def test_signal_listener_returns_false_when_no_listener(tmp_vb_dir):
    assert coord.signal_listener(signal.SIGHUP) is False


def test_reload_listener_config_no_listener(tmp_vb_dir):
    assert coord.reload_listener_config() is False


def test_reload_listener_config_version_drift_promotes_to_sigterm(tmp_vb_dir):
    """When version drifts, reload sends SIGTERM instead of SIGHUP."""
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        coord.write_atomic(coord.listener_pid_path(), str(proc.pid))
        coord.write_atomic(coord.listener_version_path(), "0.0.0-stale")

        result = coord.reload_listener_config()
        assert result is True

        # Child should receive SIGTERM and exit shortly.
        rc = proc.wait(timeout=2)
        assert rc == -signal.SIGTERM or rc != 0
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)
