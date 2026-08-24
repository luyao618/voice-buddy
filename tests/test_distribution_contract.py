# tests/test_distribution_contract.py
"""The wheel/plugin distribution contract.

Voice Buddy ships as a Claude Code plugin, not as a PyPI package. The wheel
carries the Python package only — `personas/`, `templates/`, `assets/`,
`agents/`, `hooks/` and the slash command are all delivered by the plugin.
A standalone `pip install` therefore cannot produce a working install.

That was previously indistinguishable from a working one: `voice-buddy config`
reads none of those resources, so it exited 0 in a clean wheel environment
while every persona, template and audio lookup silently returned None.

These contracts pin both halves of the decision — the supported plugin layout
resolves the real style -> template -> asset chain, and the unsupported wheel
layout refuses to pose as a working install.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.10 -> dev-only backport
    import tomli as tomllib

import pytest

from voice_buddy import config, main, response, styles
from voice_buddy.context import analyze_context

REPO_ROOT = Path(__file__).parent.parent


def _manifest():
    with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


# --- The supported layout really resolves runtime resources ------------------

def test_plugin_layout_reports_no_missing_resources():
    assert config.missing_runtime_resources() == []


def test_style_template_and_asset_resolve_end_to_end():
    """The real resolution chain, with only external TTS/playback left out.

    A clean wheel install passes `voice-buddy config` while failing every step
    below, which is precisely why config alone is not proof of runtime support.
    """
    style = styles.load_style("cute-girl")
    assert style is not None and style["id"] == "cute-girl"

    ctx = analyze_context({"hook_event_name": "SessionStart"})
    result = response.select_response(ctx, "cute-girl", "Master")
    assert result is not None and result.text

    # sessionstart is a pre-packaged event, so this must hit a real MP3.
    audio_path = main.resolve_audio_path("cute-girl", result.audio_id)
    assert audio_path is not None, f"no packaged asset for {result.audio_id}"
    assert Path(audio_path).is_file()


# --- The unsupported layout fails loudly -------------------------------------

@pytest.fixture
def resourceless_root(tmp_path, monkeypatch):
    """Point the package at a root with no runtime resources.

    This is what site-packages/ looks like after `pip install voice_buddy.whl`.
    """
    monkeypatch.setattr(config, "_REPO_ROOT", tmp_path)
    return tmp_path


def test_missing_runtime_resources_names_every_absent_directory(resourceless_root):
    assert set(config.missing_runtime_resources()) == {
        "personas", "templates", "assets",
    }


def test_missing_runtime_resources_reports_a_partial_layout(resourceless_root):
    """A half-populated root is still broken, and must say which half."""
    (resourceless_root / "personas").mkdir()
    assert set(config.missing_runtime_resources()) == {"templates", "assets"}


def test_cli_exits_nonzero_when_resources_are_missing(resourceless_root, capsys, monkeypatch):
    from voice_buddy import cli

    monkeypatch.setattr(sys, "argv", ["voice-buddy", "config"])
    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code != 0
    err = capsys.readouterr().err
    # Names what is wrong, and the supported way to fix it.
    assert "personas" in err and "templates" in err and "assets" in err
    assert "not a supported installation method" in err
    assert "/plugin install voice-buddy" in err


def test_uninstall_still_works_without_resources(resourceless_root, tmp_path, monkeypatch):
    """The way out of a broken install must not be gated by the guard.

    `uninstall` only edits settings.json. A user who ran setup before the
    resources went missing would otherwise be stuck with registered hooks and
    no supported command to remove them.
    """
    from voice_buddy import cli

    project = tmp_path / "proj"
    (project / ".claude").mkdir(parents=True)
    settings = project / ".claude" / "settings.json"
    settings.write_text(json.dumps({
        "hooks": {
            "SessionStart": [{
                "hooks": [{"type": "command", "command": "python3 -m voice_buddy"}],
                "_voice_buddy": True,
            }]
        }
    }))

    monkeypatch.setattr(
        sys, "argv", ["voice-buddy", "uninstall", "--project", str(project)]
    )
    cli.main()  # must not raise SystemExit

    remaining = json.loads(settings.read_text()).get("hooks", {})
    assert not remaining.get("SessionStart"), remaining


def test_hook_stays_silent_but_logs_actionably(resourceless_root, caplog):
    """A hook must never disrupt the session, but must not fail invisibly.

    Before this contract the hook returned normally with only DEBUG noise, so a
    broken install looked exactly like "nothing to say" in the log.
    """
    caplog.set_level("WARNING", logger="voice_buddy")

    # Returns normally — no raise, no sys.exit.
    main.handle_hook_event({"hook_event_name": "SessionStart"})

    assert "cannot speak" in caplog.text
    assert "/plugin install voice-buddy" in caplog.text


def test_hook_does_not_reach_config_or_playback_without_resources(
    resourceless_root, monkeypatch
):
    """The guard short-circuits before any config read or audio work."""
    def fail(*a, **k):
        raise AssertionError("resource-less install must not reach this path")

    monkeypatch.setattr(main, "load_user_config", fail)
    monkeypatch.setattr(main, "play_audio", fail)
    monkeypatch.setattr(main, "synthesize_to_file", fail)

    main.handle_hook_event({"hook_event_name": "SessionStart"})


# --- Metadata and CI encode the same contract --------------------------------

def test_pyproject_marks_the_project_as_not_for_pypi():
    """`Private :: Do Not Upload` is unregistered, so PyPI rejects the upload.

    That makes "we do not publish this" enforced rather than merely documented.
    """
    assert "Private :: Do Not Upload" in _manifest()["project"]["classifiers"]


def test_wheel_packages_only_the_python_package():
    """Plugin directories must not be bundled without a demonstrated need.

    The selected contract shows none: Claude Code reads them from the plugin
    root by path, and a second packaged copy is what would let the two drift.
    """
    assert _manifest()["tool"]["setuptools"]["packages"] == ["voice_buddy"]


def _workflow():
    return (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()


def test_ci_does_not_treat_bare_config_as_proof_of_runtime_support():
    """`voice-buddy config` passes in an install that cannot speak."""
    workflow = _workflow()
    bare_config_proof = re.search(
        r"^\s*\S*voice-buddy config\s*(>/dev/null)?\s*$", workflow, re.MULTILINE
    )
    assert bare_config_proof is None, (
        "CI runs `voice-buddy config` as a standalone success check; it exits 0 "
        "in a wheel-only install where every resource lookup returns None"
    )


def test_ci_asserts_the_wheel_install_fails_loudly():
    workflow = _workflow()
    assert "not a supported installation method" in workflow
    assert "wheel-only install reported success" in workflow


def test_ci_verifies_the_plugin_layout_resolves_resources():
    assert "missing_runtime_resources" in _workflow()


# --- Documentation states the contract in both languages ---------------------

def _readme():
    return (REPO_ROOT / "README.md").read_text()


def test_readme_documents_the_distribution_contract_in_both_languages():
    readme = _readme()
    split = readme.find("## 中文")
    assert split > 0, "Chinese section not found"
    english, chinese = readme[:split], readme[split:]

    assert "Distribution contract" in english
    assert "pip install voice-buddy" in english

    assert "分发契约" in chinese
    assert "pip install voice-buddy" in chinese


def test_readme_does_not_advertise_pip_install_of_the_package():
    """A bare `pip install voice-buddy` must never read as a supported path.

    Every occurrence has to sit in a line that marks it unsupported; the
    development install is `-e .` from a checkout and is spelled differently.
    """
    offenders = []
    for i, line in enumerate(_readme().splitlines(), 1):
        if re.search(r"pip3? install\s+['\"]?voice-buddy", line):
            marked = any(
                token in line
                for token in ("not supported", "不支持", "✗", "not a supported")
            )
            if not marked:
                offenders.append(f"{i}: {line.strip()}")
    assert not offenders, (
        "README shows pip install voice-buddy without marking it unsupported:\n"
        + "\n".join(offenders)
    )
