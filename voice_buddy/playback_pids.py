"""Tracks PIDs of currently-playing audio subprocesses.

Concurrency model (per plan §4):
  - add(pid):    O_APPEND atomic write of "<pid>\\n" (no lock; <PIPE_BUF on Darwin)
  - snapshot():  read file, filter via os.kill(pid, 0); returns live PIDs only
  - kill_all():  flock(playback_pids.lock) LOCK_EX -> snapshot -> SIGTERM each ->
                 truncate(0); returns count killed
  - compact():   flock(playback_pids.lock) LOCK_EX -> rewrite tmp file with live
                 PIDs only -> atomic rename
  - remove():    NO-OP at natural process exit (snapshot filter handles it)

This eliminates the rewrite-vs-kill_all race by collapsing read-modify-write
to a single lock owner, while keeping add() lock-free on the hot playback path.
"""

from __future__ import annotations

import errno
import logging
import os
import signal
import sys
import tempfile
from pathlib import Path
from typing import List

if sys.platform != "win32":
    import fcntl
else:
    fcntl = None  # type: ignore[assignment]

from voice_buddy.coord import vb_dir

logger = logging.getLogger(__name__)


def _pids_path() -> Path:
    return vb_dir() / "playback_pids"


def _lock_path() -> Path:
    return vb_dir() / "playback_pids.lock"


# --- Hot path: lock-free add -----------------------------------------------

def add(pid: int) -> None:
    """Append a PID to the playback set. Lock-free (O_APPEND atomic).

    Failure to record the PID must NOT propagate; the audio still plays.
    """
    if not isinstance(pid, int) or pid <= 0:
        return
    line = f"{pid}\n".encode("ascii")
    try:
        path = _pids_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
    except OSError as e:
        logger.debug("playback_pids.add(%d) failed: %s", pid, e)


# --- Snapshot ---------------------------------------------------------------

def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not ours
    except OSError:
        return False


def _read_all_pids() -> List[int]:
    """Read all PIDs from disk (no liveness filtering)."""
    try:
        text = _pids_path().read_text(encoding="ascii")
    except FileNotFoundError:
        return []
    except OSError:
        return []
    out: List[int] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(int(line))
        except ValueError:
            continue
    return out


def snapshot() -> List[int]:
    """Return live PIDs currently in the file (deduplicated, ordered)."""
    seen = set()
    out: List[int] = []
    for pid in _read_all_pids():
        if pid in seen:
            continue
        seen.add(pid)
        if _process_alive(pid):
            out.append(pid)
    return out


# --- Lock helper ------------------------------------------------------------

class _LockCtx:
    def __init__(self) -> None:
        self.fd = -1

    def __enter__(self) -> "_LockCtx":
        if fcntl is None:
            # Windows: no flock support, proceed without locking.
            return self
        path = _lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o644)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc) -> None:
        if fcntl is None or self.fd == -1:
            return
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass


# --- kill_all + compact -----------------------------------------------------

def kill_all(sig: int = signal.SIGTERM) -> int:
    """SIGTERM every live PID and truncate the file. Returns count killed.

    Held under playback_pids.lock so concurrent kill_all/compact are serialized.
    add() is unaffected (different lock; O_APPEND atomic).
    """
    killed = 0
    with _LockCtx():
        live = snapshot()
        for pid in live:
            try:
                os.kill(pid, sig)
                killed += 1
            except ProcessLookupError:
                continue
            except PermissionError:
                continue
            except OSError as e:
                if e.errno not in (errno.ESRCH, errno.EPERM):
                    logger.debug("kill_all: kill(%d) failed: %s", pid, e)
        # Truncate file (we just signaled all live PIDs; new add()s after this
        # point will append and be tracked normally).
        try:
            with open(_pids_path(), "w", encoding="ascii") as f:
                f.truncate(0)
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.debug("kill_all: truncate failed: %s", e)
    return killed


def compact() -> int:
    """Rewrite the file containing only live PIDs. Returns count of live PIDs.

    Trigger: every 60s OR when file exceeds 64 lines (caller's discretion).
    Atomic rewrite under the same lock.
    """
    with _LockCtx():
        live = snapshot()
        path = _pids_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="playback_pids.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="ascii") as f:
                for pid in live:
                    f.write(f"{pid}\n")
                f.flush()
                os.fsync(f.fileno())
            os.rename(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return len(live)


def needs_compaction(line_threshold: int = 64) -> bool:
    """Return True if the file has more lines than the threshold."""
    try:
        with open(_pids_path(), "rb") as f:
            return sum(1 for _ in f) > line_threshold
    except FileNotFoundError:
        return False
    except OSError:
        return False


def remove(pid: int) -> None:  # noqa: ARG001 - intentional no-op
    """Documented no-op. Natural-exit cleanup is handled by snapshot filter."""
    return None
