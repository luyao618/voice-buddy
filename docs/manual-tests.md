# Manual Tests — Hotkey Stop Playback (macOS)

These tests cover the user-facing behaviors that cannot be honestly automated
in CI (real EventTap, real audio, real keypresses). Run them on a Mac before
shipping.

Prerequisites:
- macOS
- `pip install -r requirements.txt` (installs `pyobjc-framework-Quartz`)
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
