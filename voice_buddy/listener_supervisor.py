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


# The listener blocks in CFRunLoopRun(), and CPython only runs a signal
# handler once the interpreter regains control — which happens on the run
# loop's 30s timer tick. A SIGTERM is therefore observed up to a full tick
# later (measured on a real listener: ~1.5s at best). SessionStart cannot wait
# that long, so give the graceful path a short grace period and then escalate
# to SIGKILL, which the kernel delivers without the process cooperating.
#
# SIGKILL is safe here: the target is verified to be our own listener, it owns
# no user data, and its pidfile is cleaned up by the caller. Leaving it alive
# would be worse — two EventTaps competing for F2.
SHUTDOWN_GRACE_SECONDS = 2.0
SHUTDOWN_KILL_TIMEOUT_SECONDS = 2.0
SHUTDOWN_POLL_INTERVAL = 0.05

# Sentinel for "a live process holds the pidfile but we cannot verify it".
# Distinct from None ("nothing to retire") because the two demand opposite
# responses: None allows cleanup and spawn, UNVERIFIABLE forbids both.
UNVERIFIABLE = "unverifiable"


def _retire_superseded_listener() -> Optional[bool]:
    """Terminate a verified old listener before spawning its replacement.

    Called under coord.lock when the liveness check failed but a process may
    still be holding the pidfile — the version-drift case after an upgrade.

    Every signal is gated on a stable `(pid, identity)` handle rather than a
    bare PID. The old listener can exit between SIGTERM and the escalation, and
    the kernel can hand its number to an unrelated process in that window; a
    check against the integer alone would then aim SIGKILL at a bystander.

    Returns True if the listener is gone, False if it would not die, and None
    if there was nothing verifiably ours to retire.
    """
    target = coord.get_listener_target()
    if target is None:
        # Nothing we may signal. Three situations hide here, and only one of
        # them forbids spawning:
        #   - no process at all            -> safe to clean up and spawn
        #   - a live FOREIGN process       -> the PID was recycled onto someone
        #                                     else; our listener is gone, so
        #                                     cleanup and spawn are safe
        #   - a live process we cannot classify (ps unavailable) -> it may
        #     still be our listener holding an EventTap, so changing anything
        #     risks a duplicate
        pid = coord._read_listener_pid()
        if (pid is not None
                and coord._process_alive(pid)
                and coord.process_ownership(pid) == coord.UNKNOWN):
            log.warning(
                "listener pid=%s is alive but ownership is unverifiable; "
                "leaving it alone", pid,
            )
            return UNVERIFIABLE
        return None  # nothing verifiably ours to retire
    pid, identity = target

    log.info("retiring superseded listener pid=%s", pid)
    if not _signal_and_wait(pid, identity, signal.SIGTERM, SHUTDOWN_GRACE_SECONDS):
        # Still there: the run loop has not reached a tick. Escalate — but only
        # if this is provably still the same process we set out to stop.
        if not coord.still_same_owned_process(pid, identity):
            log.info("listener pid=%s is gone (identity changed); not escalating", pid)
            return True
        log.warning("listener pid=%s ignored SIGTERM; escalating to SIGKILL", pid)
        if not _signal_and_wait(pid, identity, signal.SIGKILL,
                                SHUTDOWN_KILL_TIMEOUT_SECONDS):
            log.error(
                "listener pid=%s survived SIGKILL; not spawning a replacement",
                pid,
            )
            return False
    log.info("superseded listener pid=%s exited", pid)
    return True


def _signal_and_wait(pid: int, identity: str, sig: int, timeout: float) -> bool:
    """Signal `pid` and wait for it to exit. True if that process is gone.

    Re-confirms the identity immediately before delivering the signal, and
    treats an identity change during the wait as "exited": the process we
    wanted gone is gone, whatever now holds its number.
    """
    if not coord.still_same_owned_process(pid, identity):
        return True  # already exited; the PID may now be someone else's

    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return True  # exited between the check and the signal
    except OSError as e:
        log.warning("could not signal listener %s with %s: %s", pid, sig, e)
        return False

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _same_process_still_running(pid, identity):
            return True
        time.sleep(SHUTDOWN_POLL_INTERVAL)
    return not _same_process_still_running(pid, identity)


def _same_process_still_running(pid: int, identity: str) -> bool:
    """True iff the original process is still there under the same identity."""
    if not coord._process_alive(pid):
        return False
    return coord.process_identity(pid) == identity


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
            retired = _retire_superseded_listener()
            if retired is UNVERIFIABLE:
                # A live process holds the pidfile and we cannot prove whose it
                # is. It may still own an EventTap, so deleting its artifacts
                # and spawning would risk two listeners fighting over F2.
                # Change nothing and try again next session.
                return False
            if retired is False:
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
