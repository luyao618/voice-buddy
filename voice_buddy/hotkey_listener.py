"""macOS global F-key listener that kills currently-playing audio on press.

Runs as a singleton subprocess spawned by SessionStart. The listener:
  1. Creates a Quartz EventTap at session-event-tap level (global scope).
  2. Writes listener.pid + listener.version ONLY after the tap is enabled
     (readiness invariant per plan §2.3).
  3. Calls playback_pids.kill_all() on configured F-key press.
  4. Re-reads config on SIGHUP; rebuilds the tap if hotkey changed.
  5. Exits gracefully on SIGTERM, removing pidfile.
  6. Self-exits via 30s idle timer when sessions/ is empty (plan §3),
     re-acquiring coord.lock to close the spawn-vs-exit race.

This module imports pyobjc lazily so the import path itself is safe to
reference from cross-platform helpers; calling main() on non-darwin raises.
"""

from __future__ import annotations

import logging
import os
import signal
import sys

import voice_buddy
from voice_buddy import coord, playback_pids
from voice_buddy.config import load_user_config
from voice_buddy.keymap import name_to_keycode

log = logging.getLogger("voice_buddy.hotkey_listener")

# State held in module globals because Quartz callbacks are C-style and need
# to reach Python state without closures.
_state = {
    "current_keycode": None,   # int or None
    "tap_ref": None,
    "run_loop_source": None,
    "config_dirty": False,
    "self_exiting": False,     # set True when idle-tick initiates shutdown
}


def _configure_logging() -> None:
    log_path = coord.listener_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    ))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _check_darwin() -> None:
    if sys.platform != "darwin":
        raise RuntimeError(
            "voice_buddy.hotkey_listener requires macOS (sys.platform=darwin); "
            f"current platform: {sys.platform}"
        )


# --- EventTap callback ------------------------------------------------------

def _make_keydown_callback():
    """Build the Quartz event-tap callback closure.

    Imported here so non-darwin callers don't pay for pyobjc.
    """
    import Quartz  # type: ignore[import-not-found]

    def callback(proxy, event_type, event, refcon):  # noqa: ARG001
        try:
            # Only handle keydown events.
            if event_type != Quartz.kCGEventKeyDown:
                # Re-enable tap on timeout/disable events.
                if event_type in (
                    Quartz.kCGEventTapDisabledByTimeout,
                    Quartz.kCGEventTapDisabledByUserInput,
                ):
                    tap = _state.get("tap_ref")
                    if tap is not None:
                        Quartz.CGEventTapEnable(tap, True)
                        log.info("event tap re-enabled after disable event=%s", event_type)
                return event

            keycode = Quartz.CGEventGetIntegerValueField(
                event, Quartz.kCGKeyboardEventKeycode,
            )
            target = _state.get("current_keycode")
            if target is not None and int(keycode) == int(target):
                killed = playback_pids.kill_all(signal.SIGTERM)
                log.info("HOTKEY_FIRED keycode=%s killed=%d", keycode, killed)
        except Exception as exc:
            log.exception("event tap callback error: %s", exc)
        return event

    return callback


def _install_event_tap(keycode: int):
    """Create and enable a session-level event tap for keydown events."""
    import Quartz  # type: ignore[import-not-found]

    callback = _make_keydown_callback()
    event_mask = (1 << Quartz.kCGEventKeyDown)

    tap = Quartz.CGEventTapCreate(
        Quartz.kCGSessionEventTap,       # global, session-scope
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionListenOnly,  # don't swallow the key
        event_mask,
        callback,
        None,
    )
    if tap is None:
        return None, None

    run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    Quartz.CFRunLoopAddSource(
        Quartz.CFRunLoopGetCurrent(),
        run_loop_source,
        Quartz.kCFRunLoopCommonModes,
    )
    Quartz.CGEventTapEnable(tap, True)
    _state["current_keycode"] = keycode
    _state["tap_ref"] = tap
    _state["run_loop_source"] = run_loop_source
    log.info("EventTap installed keycode=%s", keycode)
    return tap, run_loop_source


def _remove_event_tap() -> None:
    import Quartz  # type: ignore[import-not-found]

    src = _state.get("run_loop_source")
    if src is not None:
        try:
            Quartz.CFRunLoopRemoveSource(
                Quartz.CFRunLoopGetCurrent(),
                src,
                Quartz.kCFRunLoopCommonModes,
            )
        except Exception:
            pass
    tap = _state.get("tap_ref")
    if tap is not None:
        try:
            Quartz.CGEventTapEnable(tap, False)
        except Exception:
            pass
    _state["tap_ref"] = None
    _state["run_loop_source"] = None


# --- Signal handlers (set Python-side flags only; CFRunLoop drains them) ---

def _on_sighup(signum, frame):  # noqa: ARG001
    _state["config_dirty"] = True
    log.info("SIGHUP received; will reload config on next tick")


def _on_sigterm(signum, frame):  # noqa: ARG001
    log.info("SIGTERM received; stopping run loop")
    _stop_runloop()


def _stop_runloop() -> None:
    try:
        import Quartz  # type: ignore[import-not-found]
        Quartz.CFRunLoopStop(Quartz.CFRunLoopGetCurrent())
    except Exception as e:
        log.debug("CFRunLoopStop failed: %s", e)


def _install_signal_handlers() -> None:
    signal.signal(signal.SIGHUP, _on_sighup)
    signal.signal(signal.SIGTERM, _on_sigterm)
    signal.signal(signal.SIGINT, _on_sigterm)


# --- Idle timer: reload config + self-exit if sessions empty ---------------

def _idle_tick():
    """Called every 30s by CFRunLoopTimer. Returns nothing (side-effects only).

    Responsibilities:
      1. Apply pending SIGHUP config reload.
      2. Compact playback_pids if needed.
      3. If sessions/ is empty, acquire coord.lock and self-exit.
    """
    try:
        if _state["config_dirty"]:
            _state["config_dirty"] = False
            _apply_config_reload()

        # Periodic compaction.
        if playback_pids.needs_compaction():
            try:
                playback_pids.compact()
            except Exception as e:
                log.debug("compaction failed: %s", e)

        # Self-exit check (under same lock used by SessionStart spawn).
        with coord.coord_lock():
            sessions = list(coord.sessions_dir().glob("*.alive"))
            if not sessions:
                log.info("SELF_EXIT sessions_empty=true")
                # Remove our pidfile + version while still holding the lock,
                # then mark self_exiting so main()'s finally block skips
                # redundant unlink (which would race with a new listener).
                try:
                    coord.listener_pid_path().unlink()
                except FileNotFoundError:
                    pass
                try:
                    coord.listener_version_path().unlink()
                except FileNotFoundError:
                    pass
                _state["self_exiting"] = True
                # Stop the run loop; main()'s finally block handles tap cleanup.
                _stop_runloop()
    except Exception as e:
        log.exception("idle tick error: %s", e)


def _apply_config_reload() -> None:
    """Re-read user config; rebuild EventTap if hotkey changed."""
    try:
        cfg = load_user_config()
    except Exception as e:
        log.exception("config reload failed: %s", e)
        return

    if not cfg.get("hotkey_enabled", True) or not cfg.get("enabled", True):
        # Disable tap entirely.
        if _state.get("tap_ref") is not None:
            _remove_event_tap()
            log.info("hotkey disabled by config; tap removed")
        _state["current_keycode"] = None
        return

    try:
        new_keycode = name_to_keycode(cfg.get("hotkey", "F2"))
    except ValueError as e:
        log.error("invalid hotkey in config: %s", e)
        return

    if new_keycode != _state.get("current_keycode") or _state.get("tap_ref") is None:
        _remove_event_tap()
        tap, _ = _install_event_tap(new_keycode)
        if tap is None:
            log.error("could not reinstall tap on reload (Accessibility revoked?)")
        else:
            log.info("hotkey rebound to %s (keycode=%d)", cfg.get("hotkey"), new_keycode)


# --- Main entry point ------------------------------------------------------

def _write_readiness_files() -> None:
    """Write listener.version then listener.pid (atomic, last)."""
    coord.write_atomic(coord.listener_version_path(), voice_buddy.__version__)
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))


def _record_accessibility_error() -> None:
    coord.write_atomic(
        coord.listener_error_path(),
        f"ACCESSIBILITY_NOT_GRANTED\npython={sys.executable}\n",
    )


def main() -> int:
    _check_darwin()
    _configure_logging()

    try:
        cfg = load_user_config()
    except Exception as e:
        log.exception("could not load config: %s", e)
        return 3

    if not cfg.get("hotkey_enabled", True):
        log.info("hotkey disabled in config; exiting")
        return 0

    try:
        keycode = name_to_keycode(cfg.get("hotkey", "F2"))
    except ValueError as e:
        log.error("invalid hotkey: %s", e)
        return 4

    # Install tap BEFORE writing readiness files.
    tap, _src = _install_event_tap(keycode)
    if tap is None:
        log.error("CGEventTapCreate returned NULL — Accessibility not granted? "
                  "python=%s", sys.executable)
        _record_accessibility_error()
        return 2

    _install_signal_handlers()
    _write_readiness_files()
    log.info("READY pid=%d version=%s hotkey=%s", os.getpid(),
             voice_buddy.__version__, cfg.get("hotkey"))

    try:
        # Schedule idle timer.
        import Quartz  # type: ignore[import-not-found]

        def _timer_callback(timer, info):  # noqa: ARG001
            _idle_tick()

        timer = Quartz.CFRunLoopTimerCreate(
            None,                                    # allocator
            Quartz.CFAbsoluteTimeGetCurrent() + 30,  # fire date
            30,                                      # interval
            0, 0,                                    # flags, order
            _timer_callback,
            None,
        )
        Quartz.CFRunLoopAddTimer(
            Quartz.CFRunLoopGetCurrent(),
            timer,
            Quartz.kCFRunLoopCommonModes,
        )

        Quartz.CFRunLoopRun()
    finally:
        _remove_event_tap()
        # Only remove pidfile/version if NOT self-exiting (idle_tick already
        # removed them under coord.lock; removing again would race with a
        # newly-spawned replacement listener).
        if not _state.get("self_exiting"):
            try:
                coord.listener_pid_path().unlink()
            except FileNotFoundError:
                pass
            try:
                coord.listener_version_path().unlink()
            except FileNotFoundError:
                pass
        log.info("listener exiting")

    return 0


if __name__ == "__main__":
    sys.exit(main())
