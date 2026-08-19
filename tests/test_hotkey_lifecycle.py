# tests/test_hotkey_lifecycle.py
"""Process-lifecycle and cross-platform contracts for the F2 hotkey (YAO-341).

Covers the failure modes that only show up after the listener dies uncleanly or
the machine runs more than one Claude Code session, plus the guarantee that
non-macOS installs never need Quartz.
"""
import os
import subprocess
import sys
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
    monkeypatch.setattr(coord, "_process_is_listener", lambda pid: True)


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
        assert coord._process_is_listener(4242) is True


def test_ownership_probe_fails_open_when_ps_is_unusable(tmp_vb_dir):
    """If we cannot tell, assume ours: never kill or duplicate on ambiguity."""
    with mock.patch("subprocess.run", side_effect=OSError("no ps")):
        assert coord._process_is_listener(4242) is True


def test_ownership_probe_treats_missing_pid_as_gone(tmp_vb_dir):
    with mock.patch("subprocess.run") as run:
        run.return_value = mock.Mock(returncode=1, stdout="")
        assert coord._process_is_listener(4242) is False


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

    monkeypatch.setattr(coord, "_process_is_listener", lambda pid: True)
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
