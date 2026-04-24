"""Coordination primitives shared by hotkey listener, supervisor, and CLI.

Layout under VB_DIR (= ~/Library/Application Support/voice-buddy on macOS):

    coord.lock              flock target serializing listener spawn / self-exit
    listener.pid            owned by listener; existence => EventTap installed
    listener.version        voice_buddy.__version__ string written atomically
    sessions/<id>.alive     one per active Claude Code session
    playback_pids           append-only PID-per-line file
    playback_pids.lock      flock target for kill_all + compaction
    logs/hotkey-listener.log

All file mutations use tmp + os.rename for atomicity.

This module is platform-agnostic (no pyobjc imports) so it can be used by
the CLI and hooks on any OS without paying the macOS-only import cost.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

if sys.platform != "win32":
    import fcntl
else:
    fcntl = None  # type: ignore[assignment]

from voice_buddy import config as _config

logger = logging.getLogger(__name__)


# --- Path helpers -----------------------------------------------------------

def vb_dir() -> Path:
    """Return the voice-buddy state directory, creating it if needed."""
    d = _config.get_config_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / "sessions").mkdir(exist_ok=True)
    (d / "logs").mkdir(exist_ok=True)
    return d


def coord_lock_path() -> Path:
    return vb_dir() / "coord.lock"


def listener_pid_path() -> Path:
    return vb_dir() / "listener.pid"


def listener_version_path() -> Path:
    return vb_dir() / "listener.version"


def listener_error_path() -> Path:
    return vb_dir() / "listener.error"


def sessions_dir() -> Path:
    d = vb_dir() / "sessions"
    d.mkdir(exist_ok=True)
    return d


def session_alive_path(session_id: str) -> Path:
    # Sanitize: session_id should be alnum/dash/underscore. Be defensive.
    safe = "".join(c for c in str(session_id) if c.isalnum() or c in "-_") or "anon"
    return sessions_dir() / f"{safe}.alive"


def listener_log_path() -> Path:
    return vb_dir() / "logs" / "hotkey-listener.log"


# --- Atomic write -----------------------------------------------------------

def write_atomic(path: Path, content: str) -> None:
    """Write content to path atomically via tmp + os.rename.

    Uses a tmp file in the same directory so os.rename is atomic on APFS.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# --- coord.lock context manager --------------------------------------------

@contextmanager
def coord_lock(blocking: bool = True) -> Iterator[None]:
    """Acquire the coord.lock flock for serializing spawn/exit decisions.

    Per plan §2 and §3: SessionStart and listener self-exit MUST acquire the
    same lock to close the spawn-vs-exit TOCTOU window. Lock is per-fd, so
    a fresh fd is opened for each critical section.

    Released by `flock(LOCK_UN)` and again automatically when the fd closes.
    Kernel releases the lock on process death — crash-safe.
    """
    if fcntl is None:
        # Windows: no flock support, yield without locking.
        yield
        return

    lock_path = coord_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        op = fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, op)
        try:
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


# --- Listener liveness -----------------------------------------------------

def _read_listener_pid() -> Optional[int]:
    try:
        text = listener_pid_path().read_text(encoding="utf-8").strip()
        return int(text) if text else None
    except (FileNotFoundError, ValueError, OSError):
        return None


def _read_listener_version() -> Optional[str]:
    try:
        return listener_version_path().read_text(encoding="utf-8").strip() or None
    except (FileNotFoundError, OSError):
        return None


def _process_alive(pid: int) -> bool:
    """Return True iff the process is alive (signal 0 is a no-op probe)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we don't own it — treat as alive (don't respawn).
        return True
    except OSError:
        return False


def listener_alive(version_check: bool = True) -> bool:
    """Return True iff a live, version-compatible listener is running.

    A listener is "alive" when:
      1. listener.pid file exists and contains a valid integer PID
      2. kill -0 against that PID succeeds
      3. (if version_check) listener.version matches voice_buddy.__version__

    Failure of any condition returns False so the supervisor will spawn fresh.
    """
    pid = _read_listener_pid()
    if pid is None or not _process_alive(pid):
        return False
    if version_check:
        from voice_buddy import __version__ as my_version
        listener_ver = _read_listener_version()
        if listener_ver != my_version:
            return False
    return True


def get_listener_pid() -> Optional[int]:
    """Return the live listener PID or None."""
    pid = _read_listener_pid()
    if pid is not None and _process_alive(pid):
        return pid
    return None


def cleanup_stale_listener_artifacts() -> None:
    """Best-effort removal of dead-listener pidfile + version + error marker.

    Called by SessionStart inside coord.lock when liveness check fails.
    """
    for p in (listener_pid_path(), listener_version_path(), listener_error_path()):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.debug("cleanup_stale_listener_artifacts: %s: %s", p, e)


# --- Convenience: signal listener ------------------------------------------

def signal_listener(sig: int) -> bool:
    """Send a signal to the running listener. Returns True if delivered."""
    pid = get_listener_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, sig)
        return True
    except (ProcessLookupError, PermissionError, OSError) as e:
        logger.debug("signal_listener(%s) failed: %s", sig, e)
        return False


def reload_listener_config() -> bool:
    """Send SIGHUP to listener (or SIGTERM+respawn on version drift).

    Returns True if a reload signal was sent (or respawn was triggered).
    """
    pid = _read_listener_pid()
    if pid is None or not _process_alive(pid):
        return False
    from voice_buddy import __version__ as my_version
    listener_ver = _read_listener_version()
    if listener_ver != my_version:
        # Version drift: terminate stale listener; SessionStart will respawn.
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except OSError:
            return False
    try:
        os.kill(pid, signal.SIGHUP)
        return True
    except OSError:
        return False
