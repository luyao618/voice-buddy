"""Track identities of currently-playing audio subprocesses.

Every mutation uses ``playback_pids.lock``. Registry rows pair a PID with the
process start time returned by :func:`voice_buddy.coord.process_identity`; a
bare PID is never enough authority to signal because the kernel may recycle it.

Legacy bare-PID rows and malformed rows are discarded on the next compaction or
stop operation without being signaled.
"""

from __future__ import annotations

import errno
import logging
import os
import signal
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List

if sys.platform != "win32":
    import fcntl
else:
    fcntl = None  # type: ignore[assignment]

from voice_buddy import coord

logger = logging.getLogger(__name__)


def _pids_path() -> Path:
    return coord.vb_dir() / "playback_pids"


def _lock_path() -> Path:
    return coord.vb_dir() / "playback_pids.lock"


@dataclass(frozen=True)
class _Entry:
    pid: int
    identity: str


# --- Lock helper ------------------------------------------------------------

class _LockCtx:
    def __init__(self) -> None:
        self.fd = -1

    def __enter__(self) -> "_LockCtx":
        if fcntl is None:
            # The hotkey is macOS-only. Keep imports safe on Windows, where
            # process identity is unavailable and add() therefore records none.
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


# --- Registration -----------------------------------------------------------

def add(pid: int) -> None:
    """Register a playback process using its stable process identity.

    Failure to identify or record the process must not break audio playback.
    """
    if not isinstance(pid, int) or pid <= 0:
        return
    identity = coord.process_identity(pid)
    if identity is None:
        logger.debug("playback_pids.add(%d): identity unavailable", pid)
        return
    line = f"{pid}\t{identity}\n"
    try:
        with _LockCtx():
            path = _pids_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
    except OSError as e:
        logger.debug("playback_pids.add(%d) failed: %s", pid, e)


# --- Registry I/O -----------------------------------------------------------

def _read_entries() -> List[_Entry]:
    """Read valid identity-bearing rows; legacy bare PIDs are fail-closed."""
    try:
        text = _pids_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    out: List[_Entry] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        fields = line.split("\t", 1)
        if len(fields) != 2:
            logger.debug("discarding legacy or malformed playback row")
            continue
        try:
            pid = int(fields[0])
        except ValueError:
            continue
        identity = fields[1].strip()
        if pid > 0 and identity:
            out.append(_Entry(pid, identity))
    return out


def _write_entries(entries: List[_Entry]) -> None:
    """Atomically replace the registry with ``entries``. Caller holds the lock."""
    path = _pids_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix="playback_pids.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(f"{entry.pid}\t{entry.identity}\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _entry_is_current(entry: _Entry) -> bool:
    """Return whether the row still names the same live, non-zombie process."""
    if not coord._process_alive(entry.pid):
        return False
    return coord.process_identity(entry.pid) == entry.identity


def _current_entries() -> List[_Entry]:
    seen = set()
    out = []
    for entry in _read_entries():
        key = (entry.pid, entry.identity)
        if key in seen:
            continue
        seen.add(key)
        if _entry_is_current(entry):
            out.append(entry)
    return out


def snapshot() -> List[int]:
    """Return PIDs whose stored identity still matches, deduplicated in order."""
    return [entry.pid for entry in _current_entries()]

def kill_all(sig: int = signal.SIGTERM) -> int:
    """Signal every verified playback process and return the delivered count.

    Invalid, dead, recycled, and legacy entries are discarded without signaling.
    Entries kept because of an unexpected signal error remain available to retry.
    """
    killed = 0
    with _LockCtx():
        remaining = []
        for entry in _current_entries():
            # Revalidate immediately before the non-zero signal.
            if not _entry_is_current(entry):
                continue
            try:
                os.kill(entry.pid, sig)
                killed += 1
            except ProcessLookupError:
                continue
            except PermissionError:
                remaining.append(entry)
                continue
            except OSError as e:
                if e.errno not in (errno.ESRCH, errno.EPERM):
                    logger.debug(
                        "kill_all: kill(%d) failed: %s", entry.pid, e
                    )
                remaining.append(entry)
        try:
            _write_entries(remaining)
        except OSError as e:
            logger.debug("kill_all: registry rewrite failed: %s", e)
    return killed


def compact() -> int:
    """Rewrite the registry with current identity-bearing entries only.

    Trigger: every 60s OR when file exceeds 64 lines (caller's discretion).
    """
    with _LockCtx():
        current = _current_entries()
        _write_entries(current)
        return len(current)


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
