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

            # 3. Cleanup stale artifacts.
            coord.cleanup_stale_listener_artifacts()

            # 4. Spawn detached listener.
            try:
                _spawn_detached_listener()
            except OSError as e:
                log.error("could not spawn hotkey listener: %s", e)
                return False

            # 5. Synchronous readiness poll, ≤300ms.
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
