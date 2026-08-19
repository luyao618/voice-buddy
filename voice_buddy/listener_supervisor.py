"""Spawn-or-attach helper for the singleton hotkey listener.

Per plan §2.1 (SessionStart) and §2.2 (SessionEnd):

- SessionStart:
    1. Acquire coord.lock LOCK_EX
    2. Touch sessions/<id>.alive (so a racing self-exit sees us)
    3. If listener_alive() → done; release lock
    4. Else: cleanup stale artifacts, Popen detached listener, poll up to
       300ms for readiness, release lock

- SessionEnd:
    1. Unlink sessions/<id>.alive (no listener signal — listener self-exits
       via its 30s idle timer per plan §3)

Hook integration is gated by sys.platform == "darwin" AND config.hotkey_enabled.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from typing import Optional

from voice_buddy import coord
from voice_buddy.config import load_user_config

log = logging.getLogger(__name__)

READINESS_TIMEOUT_SECONDS = 0.3
READINESS_POLL_INTERVAL = 0.02


def _is_supported_platform() -> bool:
    return sys.platform == "darwin"


def _hotkey_enabled() -> bool:
    try:
        cfg = load_user_config()
    except Exception:
        return False
    if not cfg.get("enabled", True):
        return False
    return bool(cfg.get("hotkey_enabled", True))


def _spawn_detached_listener() -> subprocess.Popen:
    """Spawn the listener as a fully-detached child."""
    log_path = coord.listener_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fp = open(log_path, "ab")
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "voice_buddy.hotkey_listener"],
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
    finally:
        log_fp.close()
    return proc


SHUTDOWN_TIMEOUT_SECONDS = 2.0
SHUTDOWN_POLL_INTERVAL = 0.02


def _retire_superseded_listener() -> Optional[bool]:
    """Terminate a verified old listener before spawning its replacement.

    Called under coord.lock when the liveness check failed but a process may
    still be holding the pidfile — the version-drift case after an upgrade.

    Only signals a PID that `get_listener_pid()` certifies as ours, so a
    recycled PID is left alone. Waits for the process to actually exit, because
    returning early would let the new listener install its EventTap while the
    old one still holds one.

    Returns True if a listener was retired, False if it would not die, and None
    if there was nothing to retire.
    """
    pid = coord.get_listener_pid()
    if pid is None:
        return None  # nothing verifiably ours to retire

    log.info("retiring superseded listener pid=%s", pid)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return None  # exited between the check and the signal
    except OSError as e:
        log.warning("could not signal superseded listener %s: %s", pid, e)
        return False

    deadline = time.monotonic() + SHUTDOWN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if not coord._process_alive(pid):
            log.info("superseded listener pid=%s exited", pid)
            return True
        time.sleep(SHUTDOWN_POLL_INTERVAL)

    # Still alive: spawning now would leave two EventTaps competing for F2.
    log.warning(
        "superseded listener pid=%s did not exit within %ss; not spawning a "
        "replacement this session", pid, SHUTDOWN_TIMEOUT_SECONDS,
    )
    return False


def ensure_listener_for_session(session_id: str) -> Optional[bool]:
    """Run the SessionStart spawn-or-attach protocol.

    Returns:
        True  — listener already alive or spawned and ready within budget
        False — spawned but not ready within budget (acceptable per AC11)
        None  — skipped (unsupported platform or hotkey disabled)
    """
    if not _is_supported_platform() or not _hotkey_enabled():
        return None

    try:
        with coord.coord_lock():
            # 1. Mark session alive BEFORE spawn check.
            try:
                coord.session_alive_path(session_id).write_text(
                    str(time.time()), encoding="utf-8"
                )
            except OSError as e:
                log.warning("could not write session alive file: %s", e)

            # 2. Liveness check.
            if coord.listener_alive():
                return True

            # 3. Version-drift handoff, still under the same lock.
            #
            # listener_alive() is false here for two different reasons: no
            # listener at all, or a live listener running an older version.
            # In the second case the old process still owns an EventTap and,
            # because session markers exist, its idle timer will not fire — so
            # spawning without terminating it leaves two listeners competing
            # for F2. Retire the old one first, and only if it is verifiably
            # ours.
            if _retire_superseded_listener() is False:
                # The old listener would not die. Spawning now would leave two
                # EventTaps fighting over F2, which is worse than one stale
                # hotkey; the next session tries again.
                return False

            # 4. Cleanup stale artifacts.
            coord.cleanup_stale_listener_artifacts()

            # 5. Spawn detached listener.
            try:
                _spawn_detached_listener()
            except OSError as e:
                log.error("could not spawn hotkey listener: %s", e)
                return False

            # 6. Synchronous readiness poll, ≤300ms.
            deadline = time.monotonic() + READINESS_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if coord.listener_alive():
                    return True
                time.sleep(READINESS_POLL_INTERVAL)
            log.warning("LISTENER_READY_TIMEOUT — listener may still be initializing")
            return False
    except Exception as e:
        log.exception("ensure_listener_for_session failed: %s", e)
        return False


def release_session(session_id: str) -> Optional[bool]:
    """Run the SessionEnd unlink protocol.

    Returns:
        True  — alive file removed (or already gone)
        None  — skipped (unsupported platform)
    """
    if not _is_supported_platform():
        return None
    try:
        coord.session_alive_path(session_id).unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning("could not unlink session alive file: %s", e)
        return False
    return True
