# tests/test_release_gate.py
"""Release-gate contracts: documentation accuracy and artifact hygiene (YAO-342).

These lock the claims a reader relies on before installing. The README said
"86 tests" while the suite had 362 — a number nobody updates by hand stops
being true, so it is checked here instead.

Artifact hygiene matters because a marketplace install copies the repository
verbatim: anything tracked here lands on every user's disk.
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


def _tracked_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    return [Path(p) for p in out.stdout.split("\n") if p.strip()]


def _readme():
    return (REPO_ROOT / "README.md").read_text()


# --- Version consistency ----------------------------------------------------

def test_version_is_identical_in_every_source():
    """Three files declare the version; a mismatch breaks the upgrade path.

    `listener.version` is written from `__version__` and compared against it on
    every SessionStart, so a drift between the package and the plugin manifest
    makes the supervisor retire and respawn the listener on every session.
    """
    plugin = json.loads(
        (REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())["version"]

    pyproject = re.search(
        r'^version = "([^"]+)"',
        (REPO_ROOT / "pyproject.toml").read_text(), re.M).group(1)

    package = re.search(
        r'^__version__ = "([^"]+)"',
        (REPO_ROOT / "voice_buddy" / "__init__.py").read_text(), re.M).group(1)

    assert plugin == pyproject == package, (
        f"version drift: plugin.json={plugin} pyproject={pyproject} "
        f"__init__={package}"
    )


# --- README claims checked against the repository ---------------------------

def test_readme_does_not_hardcode_a_test_count():
    """A hand-maintained test count is a claim that silently goes stale.

    The README said "86 tests" while the suite collected 362 — nobody updates
    that number, and re-deriving it here would mean reimplementing pytest's
    collection (stacked parametrize, fixture-generated cases), which drifts
    from the real count in its own way. The durable fix is to not assert a
    number in prose: CI prints the real one on every run.
    """
    stale = re.search(r"#\s*(\d+)\s+tests", _readme())
    assert stale is None, (
        f"README hardcodes a test count ({stale.group(1)}); it will go stale. "
        f"Describe the directory instead and let CI report the number."
    )


def test_readme_python_range_matches_requires_python():
    """The prerequisites line must agree with what installers enforce."""
    requires = re.search(
        r'^requires-python = "([^"]+)"',
        (REPO_ROOT / "pyproject.toml").read_text(), re.M).group(1)
    # ">=3.10,<3.15" -> floor 3.10, highest supported minor 3.14
    floor = re.search(r">=3\.(\d+)", requires).group(1)
    ceiling = int(re.search(r"<3\.(\d+)", requires).group(1)) - 1

    readme = _readme()
    assert f"3.{floor}" in readme and f"3.{ceiling}" in readme, (
        f"README does not state the supported range 3.{floor}-3.{ceiling}"
    )


def test_readme_documents_every_registered_hook_event():
    """The Supported Events table must list exactly what hooks.json registers."""
    registered = set(
        json.loads((REPO_ROOT / "hooks" / "hooks.json").read_text())["hooks"])
    readme = _readme()
    for event in registered:
        assert event in readme, f"hooks.json registers {event}; README omits it"


def test_readme_cli_commands_exist():
    """Every `voice-buddy <cmd>` the README teaches must be a real subcommand."""
    cli_source = (REPO_ROOT / "voice_buddy" / "cli.py").read_text()
    documented = set(re.findall(r"^voice-buddy ([a-z][a-z-]*)", _readme(), re.M))
    documented -= {"config"}  # covered by its own flags below

    for cmd in sorted(documented):
        assert f'"{cmd}"' in cli_source, (
            f"README documents `voice-buddy {cmd}`, which the CLI does not define"
        )


def test_english_and_chinese_sections_cover_the_same_topics():
    """Both languages must document the full lifecycle.

    Install and upgrade were covered in both; uninstall was documented in
    neither, so a user had no supported way to remove the plugin or find out
    that their settings are deliberately kept.
    """
    readme = _readme()
    split = readme.find("## 中文")
    assert split > 0, "Chinese section not found"
    english, chinese = readme[:split], readme[split:]

    topics = {
        "install": (["/plugin install"], ["/plugin install"]),
        "upgrade": (["/plugin update"], ["/plugin update"]),
        "uninstall": (["/plugin uninstall"], ["/plugin uninstall"]),
        "dependencies": (["pyobjc-framework-Quartz"], ["pyobjc-framework-Quartz"]),
        "permissions": (["Accessibility"], ["辅助功能", "Accessibility"]),
        "troubleshooting": (["hotkey-doctor"], ["hotkey-doctor"]),
    }
    missing = []
    for topic, (en_pats, zh_pats) in topics.items():
        if not any(p in english for p in en_pats):
            missing.append(f"EN:{topic}")
        if not any(p in chinese for p in zh_pats):
            missing.append(f"ZH:{topic}")
    assert not missing, f"README language sections are out of sync: {missing}"


def test_release_checklist_exists_and_names_the_manual_steps():
    """CI cannot grant Accessibility or press F2; the checklist must say so."""
    path = REPO_ROOT / "docs" / "RELEASE_CHECKLIST.md"
    assert path.exists(), "docs/RELEASE_CHECKLIST.md is missing"
    text = path.read_text()
    for required in ("plugin validate", "regen-constraints.sh",
                     "manual-tests.md", "uninstall"):
        assert required in text, f"release checklist does not mention {required}"

    """A stale pin here sends users back to the version we moved off."""
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib
    from packaging.requirements import Requirement

    with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
        manifest = tomllib.load(fh)
    quartz = next(Requirement(d) for d in manifest["project"]["dependencies"]
                  if "Quartz" in d)

    readme = _readme()
    for spec in quartz.specifier:
        assert f"{spec.operator}{spec.version}" in readme, (
            f"README's pyobjc install command is missing {spec}; "
            f"pyproject declares {quartz.specifier}"
        )


# --- Release artifact hygiene ----------------------------------------------

def test_no_tracked_file_contains_a_developer_home_path():
    """A marketplace install copies the repo verbatim onto every user's disk.

    Only *this machine's* home directory counts as a leak. Synthetic paths such
    as `/Users/victim` in the log-hygiene fixtures are the point of those tests,
    so matching `/Users/<anything>` would flag the very tests that prove paths
    are not leaked.
    """
    home = Path.home()
    real_home = str(home)
    username = home.name

    offenders = []
    for path in _tracked_files():
        full = REPO_ROOT / path
        if not full.is_file() or full.suffix in {".mp3", ".png", ".jpg"}:
            continue
        try:
            text = full.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if real_home in text or f"/Users/{username}" in text:
            offenders.append(str(path))
    assert not offenders, (
        f"paths under the developer's home directory are baked into tracked "
        f"files: {offenders}"
    )


def test_no_caches_or_build_output_are_tracked():
    tracked = {str(p) for p in _tracked_files()}
    bad = [p for p in tracked
           if "__pycache__" in p or p.endswith((".pyc", ".pyo", ".egg-info"))
           or p.startswith((".venv", "dist/", "build/"))]
    assert not bad, f"build or cache artifacts are tracked: {bad}"


def test_no_project_local_claude_config_is_tracked():
    """YAO-338 removed a .claude/ that duplicated the plugin's own hooks."""
    tracked = [str(p) for p in _tracked_files() if str(p).startswith(".claude/")]
    assert not tracked, f"project-local Claude config is tracked: {tracked}"


def test_no_credential_shaped_files_are_tracked():
    tracked = [str(p) for p in _tracked_files()]
    bad = [p for p in tracked
           if Path(p).suffix in {".pem", ".key", ".keystore", ".p12"}
           or Path(p).name in {".env", ".npmrc", ".netrc"}]
    assert not bad, f"credential-shaped files are tracked: {bad}"


# --- Plugin manifest integrity ---------------------------------------------

def test_both_manifests_are_valid_json():
    """`claude plugin validate .` silently skips plugin.json when both exist,
    so the two are parsed explicitly here as well as in CI."""
    for name in ("plugin.json", "marketplace.json"):
        path = REPO_ROOT / ".claude-plugin" / name
        json.loads(path.read_text())


def test_marketplace_entry_names_the_repository():
    data = json.loads(
        (REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    entry = data["plugins"][0]
    assert entry["source"]["source"] == "github"
    assert entry["source"]["repo"] == "luyao618/voice-buddy"


def test_every_style_has_persona_template_agent_and_audio():
    """A style missing any one of these fails only at runtime, per event.

    The expected set is fixed rather than derived from `personas/`: deriving it
    would make a deleted persona shrink the list instead of failing, so the
    test would pass while the style silently vanished from the product.
    The README advertises these seven.
    """
    expected = {
        "cute-girl", "elegant-lady", "warm-boy",
        "secretary", "steward", "cyber-girl", "kawaii",
    }
    found = {p.stem for p in (REPO_ROOT / "personas").glob("*.json")}
    assert found == expected, f"persona set changed: {found ^ expected}"

    for style in sorted(expected):
        assert (REPO_ROOT / "personas" / f"{style}.json").exists(), \
            f"{style}: missing persona"
        assert (REPO_ROOT / "templates" / f"{style}.json").exists(), \
            f"{style}: missing template"
        assert (REPO_ROOT / "agents" / f"voice-buddy-{style}.md").exists(), \
            f"{style}: missing agent"
        audio = REPO_ROOT / "assets" / "audio" / style
        assert audio.is_dir() and any(audio.glob("*.mp3")), \
            f"{style}: missing pre-packaged audio"
