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
import subprocess
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
    """Return True iff the process is alive (signal 0 is a no-op probe).

    A zombie — exited but not yet reaped by its parent — still answers
    `kill(pid, 0)`, yet holds no resources and runs no code, so it must not
    count as a live listener. Only the supervisor's own spawns can be zombies
    here (the listener is normally detached via `start_new_session`), but a
    handoff that waited on one would block for the full timeout and then refuse
    to spawn a replacement.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we don't own it — treat as alive (don't respawn).
        return True
    except OSError:
        return False
    return not _process_is_zombie(pid)


def _process_is_zombie(pid: int) -> bool:
    """Return True iff `pid` is an unreaped, already-exited process."""
    if sys.platform == "win32":
        return False
    try:
        out = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False  # no evidence; treat as a normal live process
    return out.returncode == 0 and out.stdout.strip().startswith("Z")


"""Ownership verdicts for a PID recorded in listener.pid.

`kill -0` only proves *something* holds the PID. Distinguishing the three
possible answers matters because the safe default differs by caller:

    OWNED    the PID is demonstrably our hotkey listener
    FOREIGN  the PID is demonstrably somebody else (recycled, or gone)
    UNKNOWN  we could not tell — `ps` was unavailable, timed out, or errored

A spawn decision may treat UNKNOWN as "probably alive" and skip respawning, at
worst costing the user a hotkey until the next session. A *signal* decision may
not: acting on UNKNOWN means sending SIGTERM to a process that might be
anything. Signals therefore require OWNED.
"""
OWNED = "owned"
FOREIGN = "foreign"
UNKNOWN = "unknown"


def process_identity(pid: int) -> Optional[str]:
    """Return a stable identity for `pid`, or None if it cannot be determined.

    A bare PID is not a stable handle: the kernel recycles it, so a PID that
    was ours a moment ago can belong to something else by the time the next
    signal is sent. Pairing the PID with its start time makes the handle stable
    for the lifetime of the process — a recycled PID always has a later start
    time, so the identity no longer matches.

    Returns "<pid>@<start time>", or None when `ps` gives no usable answer
    (process gone, or the probe itself failed).
    """
    if sys.platform == "win32":
        return None
    started = _ps_field(pid, "lstart=")
    if not started:
        return None
    return f"{pid}@{started}"


def _ps_field(pid: int, fmt: str) -> Optional[str]:
    """Read one `ps -o <fmt>` field for `pid`. None if unavailable."""
    try:
        out = subprocess.run(
            ["ps", "-o", fmt, "-p", str(pid)],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def process_ownership(pid: int) -> str:
    """Classify `pid` as OWNED / FOREIGN / UNKNOWN.

    Reads the process command line and looks for our listener module. Any
    failure to obtain that evidence is UNKNOWN, never a guess in either
    direction.
    """
    if sys.platform == "win32":
        # No portable `ps`; we cannot obtain evidence either way.
        return UNKNOWN
    try:
        out = subprocess.run(
            ["ps", "-o", "command=", "-p", str(pid)],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        # Includes TimeoutExpired: no evidence, so no signal authority.
        return UNKNOWN
    if out.returncode != 0:
        return FOREIGN  # ps says the pid is gone
    cmdline = out.stdout.strip()
    if not cmdline:
        return FOREIGN
    return OWNED if "voice_buddy.hotkey_listener" in cmdline else FOREIGN


def _process_is_listener(pid: int) -> bool:
    """Liveness-path view: treat UNKNOWN as ours to avoid duplicate listeners.

    Only for deciding whether to *spawn*. Never use this to authorize a signal;
    call `process_ownership(pid) == OWNED` for that.
    """
    return process_ownership(pid) != FOREIGN


def listener_alive(version_check: bool = True) -> bool:
    """Return True iff a live, version-compatible listener is running.

    A listener is "alive" when:
      1. listener.pid file exists and contains a valid integer PID
      2. kill -0 against that PID succeeds
      3. that PID is actually our listener, not a recycled stranger
      4. (if version_check) listener.version matches voice_buddy.__version__

    Failure of any condition returns False so the supervisor will spawn fresh.
    """
    pid = _read_listener_pid()
    if pid is None or not _process_alive(pid):
        return False
    if not _process_is_listener(pid):
        logger.debug("listener.pid %s belongs to another process; treating as stale", pid)
        return False
    if version_check:
        from voice_buddy import __version__ as my_version
        listener_ver = _read_listener_version()
        if listener_ver != my_version:
            return False
    return True


def get_listener_target() -> Optional[tuple]:
    """Return `(pid, identity)` for a listener that is safe to signal, else None.

    The identity travels with the PID so a caller that signals more than once —
    SIGTERM, then SIGKILL after a grace period — can confirm it is still
    talking to the same process. Between those two signals the original may
    exit and the kernel may hand its number to something else; re-checking the
    bare integer would then authorize killing a bystander.
    """
    pid = get_listener_pid()
    if pid is None:
        return None
    identity = process_identity(pid)
    if identity is None:
        # Live but unidentifiable: no stable handle, so no signal authority.
        return None
    return pid, identity


def still_same_owned_process(pid: int, identity: str) -> bool:
    """True iff `pid` is still the same process, and still verifiably ours.

    Used before every non-zero signal. A changed or missing identity means the
    original process is gone — which is the desired outcome, so callers treat
    it as "already exited" rather than escalating.
    """
    if process_identity(pid) != identity:
        return False
    return process_ownership(pid) == OWNED


def get_listener_pid() -> Optional[int]:
    """Return a PID that is safe to signal, or None.

    This is the single authorization gate for every signal path. It requires
    OWNED — not merely "not FOREIGN" — so an unreadable or slow `ps` yields no
    signal target rather than a guess. Callers that only need a liveness
    opinion should use `listener_alive()`.
    """
    pid = _read_listener_pid()
    if pid is None or not _process_alive(pid):
        return None
    if process_ownership(pid) != OWNED:
        logger.debug(
            "listener.pid %s is not verifiably ours; refusing to signal", pid
        )
        return None
    return pid


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
    """Send SIGHUP to listener (or SIGTERM on version drift).

    Reached from `on`/`off` and the hotkey config commands. Both branches route
    through `get_listener_pid()`, so a recycled PID is never signalled: this
    previously read the pidfile and signalled it directly with no ownership
    check at all.

    Returns True if a signal was delivered.
    """
    pid = get_listener_pid()
    if pid is None:
        return False
    from voice_buddy import __version__ as my_version
    listener_ver = _read_listener_version()
    # Version drift: terminate the old listener; SessionStart will respawn.
    sig = signal.SIGTERM if listener_ver != my_version else signal.SIGHUP
    try:
        os.kill(pid, sig)
        return True
    except OSError:
        return False
