# Manual Tests — Hotkey Stop Playback (macOS)

These tests cover the user-facing behaviors that cannot be honestly automated
in CI (real EventTap, real audio, real keypresses). Run them on a Mac before
shipping.

Prerequisites:
- macOS
- `pip install -c constraints.txt -e ".[dev]"` (installs `pyobjc-framework-Quartz` and pytest at the verified pins)
- voice-buddy plugin installed via Claude Code
- **System Settings → Keyboard → "Use F1, F2, etc. as standard function keys"** must be ENABLED, otherwise F2 sends "brightness up" instead of a keycode the EventTap can see
- **System Settings → Privacy & Security → Accessibility** must list and check the Python interpreter that runs voice-buddy. Run `voice-buddy hotkey-doctor` to see the exact path.

---

## AC1 — End-to-end latency (200 ms target)

1. Start a long voice playback:
   `voice-buddy test sessionstart`
2. Within ~300 ms after audio starts, press **F2**.
3. Observe: audio stops within 200 ms of keydown.

Stricter measurement (optional):
- Use `say -o /tmp/tone.aiff "the quick brown fox jumps over the lazy dog"`
- Play it via `afplay /tmp/tone.aiff &` and capture loopback through QuickTime Player or `sox` from a microphone next to the speaker.
- Measure delta between F2 press timestamp and the silence point in the recording.

---

## AC2 — Global hotkey while focus is elsewhere

1. Trigger a notification (`voice-buddy test notification`).
2. Switch focus to a browser, Slack, or any other app.
3. Press F2.
4. Observe: voice stops, even though Claude Code is not focused.

---

## AC6 — First-run Accessibility flow

1. Open System Settings → Privacy & Security → Accessibility.
2. Remove or uncheck the python interpreter listed.
3. Run `voice-buddy hotkey-doctor`.
4. Expected output includes:
   - Row "Accessibility granted" → **FAIL** with the exact `python=...` path that needs to be granted.
   - Suggested action printed.
5. Re-grant Accessibility to that exact binary, rerun `voice-buddy hotkey-doctor`. The row should flip to **OK**.

---

## AC11 — Readiness gap behavior

1. Restart Claude Code so SessionStart fires fresh.
2. Within ~200 ms of session start, press F2 (the listener subprocess is still booting).
3. Observe: voice-buddy does **not** log an error. The keypress falls through to default OS behavior. ~1 s later, F2 starts working normally.

---

## AC12 — Live config reload via SIGHUP

1. With a session running, run: `voice-buddy config --hotkey F3`
2. Output should include `(listener reloaded)`.
3. Press F3 → audio stops.
4. Press F2 → no effect (it is no longer the bound key).
5. `voice-buddy config --hotkey F2` to restore.

---

## AC13 — Multiple concurrent sessions share one listener

1. Open Claude Code in project A. Run `voice-buddy hotkey-doctor --non-interactive`
   and note the `listener liveness` pid and the `sessions registry` count.
2. Open Claude Code in project B, leaving A open. Re-run the doctor.
   - Expect: the **same** pid, and the session count incremented by one.
3. Start a long playback in A (`voice-buddy test sessionstart`) and press F2.
   Audio stops.
4. Close **only** B. Re-run the doctor in A.
   - Expect: same pid, session count back down by one, listener still alive.
5. Trigger playback in A and press F2 again → still stops.
   Closing one window must not silence the other.
6. Close A. After the listener's idle timer elapses (~30 s) the doctor reports
   no listener, and `sessions registry` is empty.

---

## AC14 — Stale listener record after an unclean kill

Covers PID reuse: the pidfile survives a `kill -9`, and the OS can hand that
number to an unrelated process.

1. With a session open, note the pid from `voice-buddy hotkey-doctor --non-interactive`.
2. `kill -9 <pid>` — an unclean kill, so the pidfile is left behind.
3. Run the doctor again. `listener liveness` must report **no live listener**,
   not the dead pid.
4. Open a new Claude Code session. A fresh listener spawns and F2 works again.
5. Optional: run `voice-buddy hotkey-restart` at any point — it stops the
   listener by pid (never by command-line pattern) and clears a stale record.
   With no listener running it prints a normal message and exits 0.

---

## AC15 — Upgrade / reinstall

1. With a session running and F2 working, reinstall or upgrade the plugin
   (`/plugin uninstall voice-buddy` then `/plugin install voice-buddy`, or
   `claude plugin update voice-buddy`).
2. Start a new session.
3. Run `voice-buddy hotkey-doctor --non-interactive`.
   - `version handshake` must show `matched=<new version>`. A listener left
     over from the previous version is terminated and respawned rather than
     reused.
   - The pid must differ from the one noted in step 1, and `pgrep -f
     voice_buddy.hotkey_listener` must show exactly one process for your user.
     Two would mean both listeners hold an EventTap and F2 behaves
     unpredictably.
4. Press F2 → playback stops, confirming the new listener holds the EventTap.
5. If Python itself was upgraded or the venv recreated, expect
   `[WARN] python interpreter … DRIFT` — Accessibility is granted per
   executable path, so re-grant it to the path the doctor reports.

> **Note on shutdown.** The listener blocks in `CFRunLoopRun()`, so CPython
> only runs its SIGTERM handler when the run loop next ticks — up to 30
> seconds later. The handoff therefore allows a short grace period and then
> sends SIGKILL. Seeing `ignored SIGTERM; escalating to SIGKILL` in
> `logs/hotkey-listener.log` during an upgrade is expected, not a fault.
