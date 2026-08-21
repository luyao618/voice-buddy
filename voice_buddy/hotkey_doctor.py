"""Diagnostic CLI for the hotkey-stop feature.

Implements plan §6 checks as a fixed-column table or JSON. The interactive
F2-press check is the only one that genuinely validates
the user's "Use F1, F2, etc. as standard function keys" preference;
synthetic CGEvents bypass the fn-key remap layer.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Callable, Dict, List, Optional

import voice_buddy
from voice_buddy import coord
from voice_buddy.config import load_user_config, save_user_config

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"
SKIP = "SKIP"


def _row(check: str, status: str, detail: str = "") -> Dict[str, str]:
    return {"check": check, "status": status, "detail": detail}


# --- Individual checks -----------------------------------------------------

def check_python_interpreter() -> Dict[str, str]:
    cfg = load_user_config()
    last = cfg.get("last_trusted_executable")
    here = sys.executable
    if last is None:
        return _row("python interpreter", OK, f"current={here} (no prior grant cached)")
    if last == here:
        return _row("python interpreter", OK, here)
    return _row(
        "python interpreter", WARN,
        f"DRIFT: granted={last} current={here} — Accessibility may be revoked",
    )


def check_pyobjc_importable() -> Dict[str, str]:
    if sys.platform != "darwin":
        return _row("pyobjc importable", SKIP, f"non-darwin platform: {sys.platform}")
    try:
        import Quartz  # type: ignore[import-not-found]  # noqa: F401
        return _row("pyobjc importable", OK, "Quartz module loaded")
    except ImportError as e:
        return _row("pyobjc importable", FAIL,
                    f"pip install 'pyobjc-framework-Quartz>=10.0,<13' — {e}")


def check_accessibility_granted() -> Dict[str, str]:
    if sys.platform != "darwin":
        return _row("Accessibility granted", SKIP, "non-darwin")
    try:
        import Quartz  # type: ignore[import-not-found]
    except ImportError:
        return _row("Accessibility granted", SKIP, "pyobjc missing (see prior row)")
    try:
        event_mask = (1 << Quartz.kCGEventKeyDown)
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            event_mask,
            lambda *a, **k: None,
            None,
        )
        if tap is None:
            return _row(
                "Accessibility granted", FAIL,
                f"CGEventTapCreate returned NULL — grant Accessibility to: {sys.executable}",
            )
        # Cache the trusted executable path.
        try:
            cfg = load_user_config()
            if cfg.get("last_trusted_executable") != sys.executable:
                cfg["last_trusted_executable"] = sys.executable
                save_user_config(cfg)
        except Exception:
            pass
        return _row("Accessibility granted", OK, sys.executable)
    except Exception as e:
        return _row("Accessibility granted", FAIL, str(e))


def check_fkey_mode_interactive(timeout_seconds: int = 10) -> Dict[str, str]:
    """The only check that genuinely validates the fn-key keyboard preference."""
    if sys.platform != "darwin":
        return _row("F-key fn-mode", SKIP, "non-darwin")
    try:
        import Quartz  # type: ignore[import-not-found]
    except ImportError:
        return _row("F-key fn-mode", SKIP, "pyobjc missing")

    cfg = load_user_config()
    hotkey_name = cfg.get("hotkey", "F2")
    from voice_buddy.keymap import name_to_keycode
    try:
        target_keycode = name_to_keycode(hotkey_name)
    except ValueError as e:
        return _row("F-key fn-mode", FAIL, str(e))

    print(f"\n>>> Please press {hotkey_name} now (within {timeout_seconds}s)…",
          flush=True)

    detected = {"hit": False}

    def cb(proxy, event_type, event, refcon):  # noqa: ARG001
        try:
            if event_type == Quartz.kCGEventKeyDown:
                kc = Quartz.CGEventGetIntegerValueField(
                    event, Quartz.kCGKeyboardEventKeycode,
                )
                if int(kc) == int(target_keycode):
                    detected["hit"] = True
                    Quartz.CFRunLoopStop(Quartz.CFRunLoopGetCurrent())
        except Exception:
            pass
        return event

    event_mask = (1 << Quartz.kCGEventKeyDown)
    tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionListenOnly,
        event_mask, cb, None,
    )
    if tap is None:
        return _row("F-key fn-mode", FAIL, "could not install probe tap")

    src = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    Quartz.CFRunLoopAddSource(
        Quartz.CFRunLoopGetCurrent(), src, Quartz.kCFRunLoopCommonModes,
    )
    Quartz.CGEventTapEnable(tap, True)

    deadline = Quartz.CFAbsoluteTimeGetCurrent() + timeout_seconds
    Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, timeout_seconds, False)

    Quartz.CGEventTapEnable(tap, False)
    Quartz.CFRunLoopRemoveSource(
        Quartz.CFRunLoopGetCurrent(), src, Quartz.kCFRunLoopCommonModes,
    )

    if detected["hit"]:
        return _row("F-key fn-mode", OK, f"{hotkey_name} keydown observed")
    return _row(
        "F-key fn-mode", WARN,
        f"{hotkey_name} not observed within {timeout_seconds}s — "
        "enable System Settings → Keyboard → 'Use F1, F2, etc. as standard function keys'",
    )


def check_fkey_mode_skipped() -> Dict[str, str]:
    if sys.platform != "darwin":
        return _row("F-key fn-mode", SKIP, "non-darwin")
    return _row(
        "F-key fn-mode", WARN,
        "skipped (--non-interactive); rerun without --non-interactive to verify",
    )


def check_coord_lock_writable() -> Dict[str, str]:
    try:
        import fcntl
        path = coord.coord_lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
        return _row("coord.lock writable", OK, str(path))
    except Exception as e:
        return _row("coord.lock writable", FAIL, str(e))


def check_listener_liveness() -> Dict[str, str]:
    if coord.listener_alive(version_check=False):
        pid = coord.get_listener_pid()
        return _row("listener liveness", OK, f"pid={pid}")
    return _row("listener liveness", WARN, "no live listener (will spawn on next SessionStart)")


def check_version_handshake() -> Dict[str, str]:
    pid = coord.get_listener_pid()
    if pid is None:
        return _row("version handshake", SKIP, "no live listener")
    try:
        ver = coord.listener_version_path().read_text(encoding="utf-8").strip()
    except OSError:
        return _row("version handshake", FAIL, "listener.version unreadable")
    if ver == voice_buddy.__version__:
        return _row("version handshake", OK, f"matched={ver}")
    return _row(
        "version handshake", WARN,
        f"DRIFT: cli={voice_buddy.__version__} listener={ver} "
        "(next config change will respawn)",
    )


def check_sessions_registry() -> Dict[str, str]:
    try:
        files = list(coord.sessions_dir().glob("*.alive"))
    except OSError as e:
        return _row("sessions registry", FAIL, str(e))
    return _row("sessions registry", OK, f"{len(files)} alive session(s)")


def check_playback_pids() -> Dict[str, str]:
    try:
        from voice_buddy import playback_pids as pp
        live = pp.snapshot()
        path = coord.vb_dir() / "playback_pids"
        try:
            file_lines = sum(1 for _ in open(path, "rb"))
        except FileNotFoundError:
            file_lines = 0
        return _row(
            "playback_pids sanity", OK,
            f"live={len(live)} file_lines={file_lines}",
        )
    except Exception as e:
        return _row("playback_pids sanity", FAIL, str(e))


# --- Driver ---------------------------------------------------------------

def run_doctor(non_interactive: bool = False, as_json: bool = False) -> int:
    rows: List[Dict[str, str]] = []
    rows.append(check_python_interpreter())
    rows.append(check_pyobjc_importable())
    rows.append(check_accessibility_granted())
    if non_interactive:
        rows.append(check_fkey_mode_skipped())
    else:
        rows.append(check_fkey_mode_interactive())
    rows.append(check_coord_lock_writable())
    rows.append(check_listener_liveness())
    rows.append(check_version_handshake())
    rows.append(check_sessions_registry())
    rows.append(check_playback_pids())

    if as_json:
        print(json.dumps({"rows": rows, "version": voice_buddy.__version__}, indent=2))
    else:
        max_check = max(len(r["check"]) for r in rows)
        for r in rows:
            print(f"  [{r['status']:<4}] {r['check']:<{max_check}}  {r['detail']}")

    # Exit code reflects worst severity.
    severities = {r["status"] for r in rows}
    if FAIL in severities:
        return 2
    if WARN in severities:
        return 1
    return 0
