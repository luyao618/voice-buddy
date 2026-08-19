# tests/test_hotkey_lifecycle.py
"""Process-lifecycle and cross-platform contracts for the F2 hotkey (YAO-341).

Covers the failure modes that only show up after the listener dies uncleanly or
the machine runs more than one Claude Code session, plus the guarantee that
non-macOS installs never need Quartz.
"""
import os
import subprocess
import sys
import time
from unittest import mock

import pytest

import voice_buddy
from voice_buddy import coord, listener_supervisor


@pytest.fixture
def tmp_vb_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("voice_buddy.config.get_config_dir", lambda: tmp_path)
    yield tmp_path


@pytest.fixture
def owned_pid(monkeypatch):
    """Treat any live PID as our listener (see test_coord.py::owned_pid)."""
    monkeypatch.setattr(coord, "process_ownership", lambda pid: coord.OWNED)


def _dead_pid():
    """A PID that is certain to be gone: spawn something and reap it."""
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


# --- Stale PID / PID reuse --------------------------------------------------

def test_dead_pid_is_not_alive(tmp_vb_dir):
    coord.write_atomic(coord.listener_pid_path(), str(_dead_pid()))
    coord.write_atomic(coord.listener_version_path(), voice_buddy.__version__)
    assert coord.listener_alive() is False


def test_recycled_pid_is_not_mistaken_for_the_listener(tmp_vb_dir):
    """The core stale-PID defect.

    `kill -0` only proves something holds the PID. After an unclean kill the
    pidfile survives and the OS recycles that number onto an unrelated process;
    without an ownership check the supervisor reads "alive", skips the respawn,
    and F2 stays dead until the file is deleted by hand.

    The pytest process is a real, live PID that is definitively *not* the
    listener, so it is exactly the impostor this must reject.
    """
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    coord.write_atomic(coord.listener_version_path(), voice_buddy.__version__)
    assert coord.listener_alive() is False


def test_recycled_pid_is_never_a_signal_target(tmp_vb_dir):
    """get_listener_pid feeds os.kill, so an impostor must not be returned."""
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    assert coord.get_listener_pid() is None


def test_signal_listener_refuses_to_signal_an_impostor(tmp_vb_dir):
    """No terminating signal may reach a PID that isn't ours.

    `os.kill(pid, 0)` is the liveness probe and is expected; what must never
    happen is a real signal like SIGTERM being delivered to a bystander.
    """
    import signal as _signal
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    real_kill = os.kill
    delivered = []

    def spy(pid, sig):
        if sig != 0:
            delivered.append((pid, sig))
            return None
        return real_kill(pid, sig)

    with mock.patch("os.kill", side_effect=spy):
        assert coord.signal_listener(_signal.SIGTERM) is False
    assert delivered == []


def test_supervisor_respawns_over_a_recycled_pid(tmp_vb_dir, monkeypatch):
    """End of the chain: a stale pidfile must not suppress the respawn."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(listener_supervisor, "_hotkey_enabled", lambda: True)
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    coord.write_atomic(coord.listener_version_path(), voice_buddy.__version__)

    with mock.patch.object(listener_supervisor, "_spawn_detached_listener") as spawn:
        listener_supervisor.ensure_listener_for_session("sid-stale")
    spawn.assert_called_once()


def test_ownership_probe_accepts_a_real_listener_command_line(tmp_vb_dir):
    """Guard the guard: the probe must not reject a genuine listener."""
    with mock.patch("subprocess.run") as run:
        run.return_value = mock.Mock(
            returncode=0,
            stdout="/usr/bin/python3 -m voice_buddy.hotkey_listener\n",
        )
        assert coord.process_ownership(4242) == coord.OWNED


@pytest.mark.parametrize("failure", [
    OSError("no ps"),
    subprocess.SubprocessError("boom"),
    subprocess.TimeoutExpired(cmd="ps", timeout=5),
])
def test_ownership_probe_reports_unknown_when_ps_is_unusable(tmp_vb_dir, failure):
    """No evidence means UNKNOWN — not a guess in either direction.

    The previous version returned True here, which `get_listener_pid()` then
    treated as authorization to signal. An unreadable `ps` could therefore
    aim SIGTERM at whatever had inherited a recycled PID.
    """
    with mock.patch("subprocess.run", side_effect=failure):
        assert coord.process_ownership(4242) == coord.UNKNOWN


def test_ownership_probe_treats_missing_pid_as_foreign(tmp_vb_dir):
    with mock.patch("subprocess.run") as run:
        run.return_value = mock.Mock(returncode=1, stdout="")
        assert coord.process_ownership(4242) == coord.FOREIGN


def test_ownership_probe_treats_another_program_as_foreign(tmp_vb_dir):
    with mock.patch("subprocess.run") as run:
        run.return_value = mock.Mock(returncode=0, stdout="/usr/bin/vim notes.txt\n")
        assert coord.process_ownership(4242) == coord.FOREIGN


def test_liveness_view_treats_unknown_as_ours(tmp_vb_dir):
    """Spawn decisions stay conservative: UNKNOWN must not trigger a duplicate.

    This is the one place the ambiguous verdict is allowed to mean "probably
    alive" — the cost is a stale hotkey, not a stray signal.
    """
    with mock.patch.object(coord, "process_ownership", return_value=coord.UNKNOWN):
        assert coord._process_is_listener(4242) is True
    with mock.patch.object(coord, "process_ownership", return_value=coord.FOREIGN):
        assert coord._process_is_listener(4242) is False


def test_signal_authorization_requires_owned_not_merely_not_foreign(tmp_vb_dir):
    """The asymmetry that fixes the blocker, stated directly."""
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    with mock.patch.object(coord, "process_ownership", return_value=coord.UNKNOWN):
        # Liveness may say "assume alive"...
        assert coord._process_is_listener(os.getpid()) is True
        # ...but no signal target is handed out.
        assert coord.get_listener_pid() is None


def test_cleanup_removes_stale_artifacts(tmp_vb_dir):
    coord.write_atomic(coord.listener_pid_path(), str(_dead_pid()))
    coord.write_atomic(coord.listener_version_path(), "0.0.0")
    coord.cleanup_stale_listener_artifacts()
    assert not coord.listener_pid_path().exists()
    assert not coord.listener_version_path().exists()


# --- Multiple concurrent sessions -------------------------------------------

def test_concurrent_sessions_each_get_their_own_marker(tmp_vb_dir):
    for sid in ("alpha", "beta", "gamma"):
        coord.session_alive_path(sid).write_text("1")
    names = sorted(p.name for p in coord.sessions_dir().glob("*.alive"))
    assert names == ["alpha.alive", "beta.alive", "gamma.alive"]


def test_ending_one_session_leaves_the_others_alive(tmp_vb_dir, monkeypatch):
    """The listener is shared, so one window closing must not silence another."""
    monkeypatch.setattr(sys, "platform", "darwin")
    for sid in ("alpha", "beta", "gamma"):
        coord.session_alive_path(sid).write_text("1")

    listener_supervisor.release_session("beta")

    remaining = sorted(p.name for p in coord.sessions_dir().glob("*.alive"))
    assert remaining == ["alpha.alive", "gamma.alive"]


def test_last_session_out_leaves_no_markers(tmp_vb_dir, monkeypatch):
    """When every session ends the registry empties, which is the listener's
    self-exit condition."""
    monkeypatch.setattr(sys, "platform", "darwin")
    for sid in ("alpha", "beta"):
        coord.session_alive_path(sid).write_text("1")
    for sid in ("alpha", "beta"):
        listener_supervisor.release_session(sid)
    assert list(coord.sessions_dir().glob("*.alive")) == []


def test_release_session_is_idempotent(tmp_vb_dir, monkeypatch):
    """SessionEnd can fire twice; the second must not raise."""
    monkeypatch.setattr(sys, "platform", "darwin")
    coord.session_alive_path("solo").write_text("1")
    assert listener_supervisor.release_session("solo") is True
    assert listener_supervisor.release_session("solo") is True


@pytest.mark.parametrize("sid", ["../escape", "a/b/c", "", "with space", "sid;rm -rf"])
def test_session_ids_cannot_escape_the_sessions_directory(tmp_vb_dir, sid):
    """session_id is attacker-adjacent input used as a filename."""
    path = coord.session_alive_path(sid)
    assert path.parent == coord.sessions_dir()
    assert "/" not in path.name.replace(".alive", "")
    assert ".." not in path.name


# --- Non-macOS: clean no-ops, no Quartz -------------------------------------

@pytest.mark.parametrize("platform", ["linux", "win32", "freebsd"])
def test_supervisor_is_a_no_op_off_darwin(tmp_vb_dir, monkeypatch, platform):
    monkeypatch.setattr(sys, "platform", platform)
    assert listener_supervisor.ensure_listener_for_session("sid") is None
    assert listener_supervisor.release_session("sid") is None


@pytest.mark.parametrize("module", [
    "voice_buddy", "voice_buddy.main", "voice_buddy.coord", "voice_buddy.cli",
    "voice_buddy.player", "voice_buddy.playback_pids", "voice_buddy.injector",
    "voice_buddy.listener_supervisor", "voice_buddy.hotkey_doctor",
    "voice_buddy.context", "voice_buddy.styles", "voice_buddy.response",
])
def test_modules_import_without_pyobjc(module):
    """A Linux/Windows install must not need Quartz to run the hooks.

    pyobjc is declared with a `sys_platform == "darwin"` marker, so it is
    genuinely absent elsewhere. Any module-level import of it would break every
    hook on those platforms, not just the hotkey.

    Imports into a throwaway module namespace rather than evicting entries from
    `sys.modules`: dropping the real modules leaves other tests holding stale
    references to superseded copies.
    """
    import importlib.util

    real_import = __import__
    blocked = []

    def guard(name, *args, **kwargs):
        if name.split(".")[0] in {"Quartz", "objc", "AppKit", "Foundation"}:
            blocked.append(name)
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    spec = importlib.util.find_spec(module)
    assert spec is not None and spec.origin, f"cannot locate {module}"
    fresh = importlib.util.module_from_spec(spec)

    with mock.patch("builtins.__import__", side_effect=guard):
        # Executes the module body in a private namespace; sys.modules is
        # untouched, so no other test sees a different object afterwards.
        spec.loader.exec_module(fresh)

    assert blocked == [], f"{module} imported pyobjc at module load: {blocked}"


def test_hotkey_doctor_skips_cleanly_without_pyobjc(monkeypatch):
    """Off darwin the doctor reports SKIP rather than failing."""
    from voice_buddy import hotkey_doctor
    monkeypatch.setattr(sys, "platform", "linux")
    row = hotkey_doctor.check_pyobjc_importable()
    assert row["status"] == hotkey_doctor.SKIP


def test_hotkey_doctor_quotes_the_current_quartz_range(monkeypatch):
    """The remediation command must match the range pyproject actually allows.

    It advertised `<12.0` after YAO-339 raised the cap to `<13`, so anyone
    following it reinstalled the version the project had just moved off.
    """
    from voice_buddy import hotkey_doctor
    monkeypatch.setattr(sys, "platform", "darwin")
    with mock.patch.dict(sys.modules, {"Quartz": None}):
        with mock.patch("builtins.__import__", side_effect=ImportError("nope")):
            row = hotkey_doctor.check_pyobjc_importable()
    assert "<12.0" not in row["detail"]
    assert "<13" in row["detail"]


def test_doctor_remediation_matches_the_declared_dependency():
    """Pin the doctor's advice to pyproject, so the two can't drift again."""
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib
    from pathlib import Path
    from packaging.requirements import Requirement

    root = Path(__file__).parent.parent
    with open(root / "pyproject.toml", "rb") as fh:
        manifest = tomllib.load(fh)
    quartz = next(Requirement(d) for d in manifest["project"]["dependencies"]
                  if "Quartz" in d)

    source = (root / "voice_buddy" / "hotkey_doctor.py").read_text()
    # Every version bound the manifest declares must appear in the advice.
    for spec in quartz.specifier:
        assert f"{spec.operator}{spec.version}" in source, (
            f"hotkey_doctor advises a range missing {spec}; pyproject says "
            f"{quartz.specifier}"
        )


# --- Scoped process management ----------------------------------------------

def test_hotkey_restart_signals_only_the_verified_listener(tmp_vb_dir, monkeypatch):
    """`pkill -f hotkey_listener` matches on command line and will signal any
    process whose arguments contain that string. This resolves the PID through
    the pidfile and verifies ownership first."""
    from voice_buddy import cli

    monkeypatch.setattr(coord, "process_ownership", lambda pid: coord.OWNED)
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))

    sent = []
    monkeypatch.setattr(coord, "signal_listener",
                        lambda sig: sent.append(sig) or True)
    assert cli.do_hotkey_restart() == 0
    assert sent and sent[0] == __import__("signal").SIGTERM


def test_hotkey_restart_is_safe_when_no_listener_runs(tmp_vb_dir):
    """No listener is a normal state, not an error."""
    from voice_buddy import cli
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))  # impostor
    assert cli.do_hotkey_restart() == 0
    # The stale pidfile is cleared so the next session starts clean.
    assert not coord.listener_pid_path().exists()


def test_docs_do_not_recommend_pattern_based_kill():
    """Documentation must not tell users to run `pkill -f hotkey_listener`.

    Verified live: that pattern matched five processes on this machine,
    including one unrelated to Voice Buddy.
    """
    from pathlib import Path
    root = Path(__file__).parent.parent
    for name in ("README.md",):
        text = (root / name).read_text()
        assert "pkill -f hotkey_listener" not in text, (
            f"{name} still recommends a pattern-based kill"
        )


# --- No signal without verified ownership, at every call site ---------------
#
# `get_listener_pid()` is the single authorization gate. These drive each
# public entry point with the ownership probe unable to answer, and assert
# that nothing beyond the `kill(pid, 0)` liveness probe is delivered.

PS_FAILURES = [
    OSError("ps unavailable"),
    subprocess.SubprocessError("ps crashed"),
    subprocess.TimeoutExpired(cmd="ps", timeout=5),
]


@pytest.fixture
def signal_spy():
    """Record every real signal; let `kill(pid, 0)` liveness probes through."""
    delivered = []
    real_kill = os.kill

    def spy(pid, sig):
        if sig != 0:
            delivered.append((pid, sig))
            return None
        return real_kill(pid, sig)

    with mock.patch("os.kill", side_effect=spy):
        yield delivered


@pytest.mark.parametrize("failure", PS_FAILURES)
def test_hotkey_restart_sends_no_signal_when_ps_fails(tmp_vb_dir, signal_spy, failure):
    """The reported exploit: `ps` broken + recycled pidfile -> innocent SIGTERM."""
    from voice_buddy import cli
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    with mock.patch("subprocess.run", side_effect=failure):
        rc = cli.do_hotkey_restart()
    assert rc == 0
    assert signal_spy == []


@pytest.mark.parametrize("failure", PS_FAILURES)
def test_config_reload_sends_no_signal_when_ps_fails(tmp_vb_dir, signal_spy, failure):
    """reload_listener_config backs `on`/`off` and the hotkey config commands."""
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    coord.write_atomic(coord.listener_version_path(), voice_buddy.__version__)
    with mock.patch("subprocess.run", side_effect=failure):
        assert coord.reload_listener_config() is False
    assert signal_spy == []


@pytest.mark.parametrize("failure", PS_FAILURES)
def test_config_reload_version_drift_sends_no_signal_when_ps_fails(
    tmp_vb_dir, signal_spy, failure
):
    """The drift branch promotes to SIGTERM, so it needs the same gate."""
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    coord.write_atomic(coord.listener_version_path(), "0.0.0-old")
    with mock.patch("subprocess.run", side_effect=failure):
        assert coord.reload_listener_config() is False
    assert signal_spy == []


@pytest.mark.parametrize("failure", PS_FAILURES)
def test_signal_listener_sends_nothing_when_ps_fails(tmp_vb_dir, signal_spy, failure):
    import signal as _signal
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    with mock.patch("subprocess.run", side_effect=failure):
        assert coord.signal_listener(_signal.SIGTERM) is False
    assert signal_spy == []


@pytest.mark.parametrize("failure", PS_FAILURES)
def test_supersede_sends_no_signal_when_ps_fails(tmp_vb_dir, signal_spy, failure):
    """The upgrade handoff must not terminate an unverified process either.

    A live PID we cannot classify reports UNVERIFIABLE rather than None: the
    caller has to tell "nothing to retire" apart from "something is there but
    we cannot prove whose it is", because only the first permits a spawn.
    """
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    coord.write_atomic(coord.listener_version_path(), "0.0.0-old")
    with mock.patch("subprocess.run", side_effect=failure):
        assert (listener_supervisor._retire_superseded_listener()
                is listener_supervisor.UNVERIFIABLE)
    assert signal_spy == []


def test_on_off_reach_reload_through_the_verified_gate(tmp_vb_dir, signal_spy):
    """`voice-buddy on` / `off` route through the same authorization."""
    from voice_buddy import cli
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    coord.write_atomic(coord.listener_version_path(), voice_buddy.__version__)
    with mock.patch("subprocess.run", side_effect=OSError("ps unavailable")), \
         mock.patch("voice_buddy.config.save_user_config"), \
         mock.patch("voice_buddy.config.load_user_config", return_value={}):
        cli.do_on()
        cli.do_off()
    assert signal_spy == []


# --- Version-drift handoff (AC15) -------------------------------------------

def test_superseded_listener_is_terminated_before_the_replacement_spawns(
    tmp_vb_dir, monkeypatch
):
    """AC15: an upgrade must leave exactly one listener, not two.

    Previously the supervisor saw the version mismatch, deleted the pid/version
    files and spawned a replacement without signalling the old process. The old
    listener kept its EventTap and, because session markers still existed, its
    idle timer never fired — two listeners competing for F2.
    """
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(listener_supervisor, "_hotkey_enabled", lambda: True)

    old = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        coord.write_atomic(coord.listener_pid_path(), str(old.pid))
        coord.write_atomic(coord.listener_version_path(), "0.0.0-old")
        monkeypatch.setattr(coord, "process_ownership", lambda pid: coord.OWNED)

        with mock.patch.object(listener_supervisor, "_spawn_detached_listener") as spawn:
            listener_supervisor.ensure_listener_for_session("sid-upgrade")

        # The old listener was terminated before the replacement was started.
        assert old.wait(timeout=5) is not None
        spawn.assert_called_once()
    finally:
        if old.poll() is None:
            old.kill()
            old.wait(timeout=5)


def test_retire_waits_for_the_old_listener_to_actually_exit(tmp_vb_dir, monkeypatch):
    """Returning before the process dies would overlap two EventTaps.

    The child delays its exit after SIGTERM, so a `_retire_superseded_listener`
    that returned immediately would be observably wrong: without the wait loop
    the process is still alive at the moment the function returns. A child that
    dies instantly cannot distinguish the two implementations.
    """
    # Catch SIGTERM, stay alive briefly, then exit — like a listener tearing
    # down its EventTap.
    slow_exit = (
        "import signal, sys, time\n"
        "def bye(sig, frm):\n"
        "    time.sleep(0.4)\n"
        "    sys.exit(0)\n"
        "signal.signal(signal.SIGTERM, bye)\n"
        "time.sleep(60)\n"
    )
    old = subprocess.Popen([sys.executable, "-c", slow_exit],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # Let the handler install before signalling.
        time.sleep(0.3)
        coord.write_atomic(coord.listener_pid_path(), str(old.pid))
        monkeypatch.setattr(coord, "process_ownership", lambda pid: coord.OWNED)

        started = time.monotonic()
        assert listener_supervisor._retire_superseded_listener() is True
        elapsed = time.monotonic() - started

        # It really waited, and the process is gone on return.
        assert elapsed >= 0.3, f"returned after only {elapsed:.3f}s — did not wait"
        assert not coord._process_alive(old.pid)
    finally:
        if old.poll() is None:
            old.kill()
        old.wait(timeout=5)


def test_sigterm_escalates_to_sigkill_when_the_run_loop_defers_it(
    tmp_vb_dir, monkeypatch
):
    """The real listener does not honour SIGTERM promptly.

    It blocks in CFRunLoopRun(), and CPython only runs the handler when the
    interpreter regains control — on the run loop's 30s tick. Measured on a
    live listener: SIGTERM was still pending 2.75s later and the process only
    exited once the tick fired. SessionStart cannot wait a full tick, so the
    handoff escalates to SIGKILL, which the kernel delivers regardless.
    """
    import signal as _signal
    monkeypatch.setattr(listener_supervisor, "SHUTDOWN_GRACE_SECONDS", 0.1)
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    monkeypatch.setattr(coord, "process_ownership", lambda pid: coord.OWNED)

    sent = []
    real_kill = os.kill
    alive = {"value": True}

    def spy(pid, sig):
        if sig == 0:
            if not alive["value"]:
                raise ProcessLookupError
            return None
        sent.append(sig)
        if sig == _signal.SIGKILL:
            alive["value"] = False  # SIGKILL cannot be deferred
        return None

    with mock.patch("os.kill", side_effect=spy):
        assert listener_supervisor._retire_superseded_listener() is True

    assert sent == [_signal.SIGTERM, _signal.SIGKILL], (
        f"expected graceful-then-forced escalation, got {sent}"
    )


def test_no_replacement_spawns_when_the_old_listener_survives_sigkill(
    tmp_vb_dir, monkeypatch
):
    """One stale hotkey beats two listeners fighting over the EventTap."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(listener_supervisor, "_hotkey_enabled", lambda: True)
    monkeypatch.setattr(listener_supervisor, "SHUTDOWN_GRACE_SECONDS", 0.05)
    monkeypatch.setattr(listener_supervisor, "SHUTDOWN_KILL_TIMEOUT_SECONDS", 0.05)
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    coord.write_atomic(coord.listener_version_path(), "0.0.0-old")
    monkeypatch.setattr(coord, "process_ownership", lambda pid: coord.OWNED)

    # Every signal is swallowed, so the "old listener" never exits.
    real_kill = os.kill
    with mock.patch("os.kill",
                    side_effect=lambda p, s: None if s != 0 else real_kill(p, s)):
        with mock.patch.object(listener_supervisor, "_spawn_detached_listener") as spawn:
            result = listener_supervisor.ensure_listener_for_session("sid-stuck")
    assert result is False
    spawn.assert_not_called()


def test_retire_is_a_no_op_when_nothing_is_running(tmp_vb_dir):
    assert listener_supervisor._retire_superseded_listener() is None


# --- Version drift with unverifiable ownership ------------------------------
#
# The dangerous combination: the recorded version is stale (so the liveness
# check fails and the supervisor wants to spawn), a process is still holding
# the pidfile, and `ps` cannot say whose it is. Doing anything here risks a
# second EventTap.

@pytest.mark.parametrize("failure", PS_FAILURES)
def test_version_drift_with_unknown_ownership_spawns_nothing(
    tmp_vb_dir, monkeypatch, failure
):
    """Zero signal, zero cleanup, zero spawn — the whole implementation path."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(listener_supervisor, "_hotkey_enabled", lambda: True)

    live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        coord.write_atomic(coord.listener_pid_path(), str(live.pid))
        coord.write_atomic(coord.listener_version_path(), "0.0.0-old")

        # Record signals locally rather than via the signal_spy fixture, whose
        # os.kill patch would otherwise still be active during teardown and
        # swallow the cleanup kill.
        delivered = []
        real_kill = os.kill

        def spy(target, sig):
            if sig != 0:
                delivered.append((target, sig))
                return None
            return real_kill(target, sig)

        # Patch only `coord`'s view of subprocess: patching the module globally
        # would also break Popen.wait() during teardown.
        with mock.patch.object(coord.subprocess, "run", side_effect=failure), \
             mock.patch("os.kill", side_effect=spy), \
             mock.patch.object(listener_supervisor, "_spawn_detached_listener") as spawn:
            result = listener_supervisor.ensure_listener_for_session("sid-unknown")

        assert result is False, "must not report success"
        spawn.assert_not_called()
        assert delivered == []
        # The artifacts describe a process that may still be live: keep them.
        assert coord.listener_pid_path().exists()
        assert coord.listener_version_path().exists()
        assert live.poll() is None, "the unverified process must be left alone"
    finally:
        live.kill()
        live.wait(timeout=5)


def test_version_drift_with_foreign_pid_does_spawn(tmp_vb_dir, monkeypatch):
    """FOREIGN is not UNKNOWN: a recycled PID means our listener is gone.

    Guards the guard — an over-broad block would strand the user with no
    listener whenever the pidfile happened to name someone else's process.
    """
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(listener_supervisor, "_hotkey_enabled", lambda: True)
    # The pytest process is alive and demonstrably not our listener.
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    coord.write_atomic(coord.listener_version_path(), "0.0.0-old")

    with mock.patch.object(listener_supervisor, "_spawn_detached_listener") as spawn:
        listener_supervisor.ensure_listener_for_session("sid-foreign")
    spawn.assert_called_once()


def test_absent_pid_with_version_drift_spawns(tmp_vb_dir, monkeypatch):
    """No process at all: cleanup and spawn are the correct response."""
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(listener_supervisor, "_hotkey_enabled", lambda: True)
    coord.write_atomic(coord.listener_pid_path(), str(_dead_pid()))
    coord.write_atomic(coord.listener_version_path(), "0.0.0-old")

    with mock.patch.object(listener_supervisor, "_spawn_detached_listener") as spawn:
        listener_supervisor.ensure_listener_for_session("sid-absent")
    spawn.assert_called_once()


# --- Stable process identity across the escalation --------------------------

def test_process_identity_pairs_pid_with_start_time(tmp_vb_dir):
    ident = coord.process_identity(os.getpid())
    assert ident is not None
    assert ident.startswith(f"{os.getpid()}@")


def test_process_identity_is_none_when_ps_is_unusable(tmp_vb_dir):
    with mock.patch("subprocess.run", side_effect=OSError("no ps")):
        assert coord.process_identity(os.getpid()) is None


def test_process_identity_differs_between_processes(tmp_vb_dir):
    """Two live processes must never share an identity."""
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        assert coord.process_identity(os.getpid()) != coord.process_identity(other.pid)
    finally:
        other.kill()
        other.wait(timeout=5)


def test_still_same_owned_process_rejects_a_changed_identity(tmp_vb_dir):
    with mock.patch.object(coord, "process_ownership", return_value=coord.OWNED):
        with mock.patch.object(coord, "process_identity", return_value="1@later"):
            assert coord.still_same_owned_process(1, "1@earlier") is False


def test_get_listener_target_refuses_an_unidentifiable_process(tmp_vb_dir):
    """No stable handle means no signal authority, even if ownership says OWNED."""
    coord.write_atomic(coord.listener_pid_path(), str(os.getpid()))
    with mock.patch.object(coord, "process_ownership", return_value=coord.OWNED), \
         mock.patch.object(coord, "process_identity", return_value=None):
        assert coord.get_listener_target() is None


def test_no_sigkill_when_the_pid_is_recycled_after_sigterm(tmp_vb_dir, monkeypatch):
    """The escalation race OC-R identified.

    The old listener exits on SIGTERM and the kernel hands its number to an
    unrelated process before the grace period elapses. Checking the bare
    integer would report "still alive" and escalate, sending SIGKILL to the
    bystander. Re-verifying the identity catches the substitution.
    """
    import signal as _signal
    pid = os.getpid()
    old = f"{pid}@Wed Aug 19 10:00:00 2026"
    new = f"{pid}@Wed Aug 19 15:30:00 2026"   # bystander inherits the PID

    state = {"identity": old}
    sent = []

    def fake_kill(target, sig):
        if sig == 0:
            return None            # something holds the PID — now the bystander
        sent.append(sig)
        if sig == _signal.SIGTERM:
            state["identity"] = new
        return None

    monkeypatch.setattr(listener_supervisor, "SHUTDOWN_GRACE_SECONDS", 0.05)
    coord.write_atomic(coord.listener_pid_path(), str(pid))

    with mock.patch.object(coord, "process_ownership", return_value=coord.OWNED), \
         mock.patch.object(coord, "process_identity",
                           side_effect=lambda p: state["identity"]), \
         mock.patch("os.kill", side_effect=fake_kill):
        result = listener_supervisor._retire_superseded_listener()

    assert _signal.SIGKILL not in sent, "SIGKILL reached a recycled PID"
    assert sent == [_signal.SIGTERM]
    assert result is True, "the original listener is gone, so this is success"


def test_no_signal_at_all_when_identity_changes_before_sigterm(tmp_vb_dir, monkeypatch):
    """The process exits between reading the pidfile and the first signal."""
    import signal as _signal
    pid = os.getpid()
    coord.write_atomic(coord.listener_pid_path(), str(pid))

    identities = iter([f"{pid}@first", f"{pid}@second", f"{pid}@second",
                       f"{pid}@second", f"{pid}@second"])
    sent = []

    def fake_kill(target, sig):
        if sig != 0:
            sent.append(sig)
        return None

    with mock.patch.object(coord, "process_ownership", return_value=coord.OWNED), \
         mock.patch.object(coord, "process_identity",
                           side_effect=lambda p: next(identities, f"{pid}@second")), \
         mock.patch("os.kill", side_effect=fake_kill):
        result = listener_supervisor._retire_superseded_listener()

    assert sent == [], "signalled a process that had already been replaced"
    assert result is True


def test_zombie_process_does_not_count_as_a_live_listener(tmp_vb_dir):
    """A zombie still answers `kill(pid, 0)` but holds no EventTap.

    Found while building the handoff test: SIGTERM landed, the child became
    `<defunct>`, and the wait loop kept seeing it as alive until the timeout —
    at which point the supervisor refused to spawn a replacement, so the
    upgrade left the user with no listener at all.
    """
    import signal as _signal
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        os.kill(proc.pid, _signal.SIGTERM)
        # Deliberately not reaped: this is the zombie window.
        for _ in range(100):
            if proc.poll() is not None or _is_defunct(proc.pid):
                break
            time.sleep(0.02)
        assert _is_defunct(proc.pid), "could not produce a zombie to test"
        assert coord._process_alive(proc.pid) is False
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)


def _is_defunct(pid):
    out = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                         capture_output=True, text=True)
    return out.returncode == 0 and out.stdout.strip().startswith("Z")
