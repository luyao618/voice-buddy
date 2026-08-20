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
import sys
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


# --- The gate must actually gate ---------------------------------------------

def _workflow():
    return (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()


def test_advisory_scan_is_blocking():
    """A release gate that reports a CVE and goes green is not a gate.

    `pip-audit` ran with `continue-on-error: true`, so any known vulnerability
    passed CI while the checklist claimed "no known vulnerabilities".
    """
    workflow = _workflow()
    assert "continue-on-error" not in workflow, (
        "a CI step is non-blocking; the release gate must fail on findings"
    )
    assert "pip_audit" in workflow, "the advisory scan is missing from CI"


def test_advisory_exceptions_are_explicit_and_documented():
    """Waivers must be auditable, never silent."""
    path = REPO_ROOT / ".pip-audit-ignore"
    assert path.exists(), ".pip-audit-ignore is missing; exceptions have no home"
    text = path.read_text()
    for required in ("reviewed", "GHSA", "Remove when"):
        assert required.lower() in text.lower(), (
            f"the exception file does not explain {required}"
        )
    # Every non-comment line must look like an advisory id.
    for line in text.splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        assert re.match(r"^(GHSA-[\w-]+|PYSEC-\d{4}-\d+)$", entry), (
            f"unrecognized exception entry: {entry!r}"
        )


def test_checklist_platform_claims_match_the_workflow():
    """The checklist claimed Linux *and Windows* runners; there is no Windows job.

    README's "Windows is best-effort" was honest while the checklist — the
    document a releaser trusts as evidence — asserted coverage that never ran.
    """
    workflow = _workflow()
    checklist = (REPO_ROOT / "docs" / "RELEASE_CHECKLIST.md").read_text()

    runs_windows = "windows-latest" in workflow
    if not runs_windows:
        # The checklist must not present Windows as executed coverage.
        table_row = next(
            (ln for ln in checklist.splitlines()
             if ln.startswith("| `test`")), "")
        assert "Windows" not in table_row, (
            "the checklist's CI table claims Windows coverage, but no Windows "
            "runner exists in the workflow"
        )
        assert "no Windows runner" in checklist, (
            "the checklist must state plainly that Windows is not run in CI"
        )
        assert "simulated" in checklist, (
            "the checklist must say win32 is only a simulated no-op contract"
        )


def test_ci_scans_artifact_contents_not_just_member_names():
    """Member names alone let embedded credentials ship.

    Demonstrated: an AWS key, a GitHub token and another developer's home
    path were all
    injected into `voice_buddy/config.py`, reached both the wheel and the
    sdist, and the name-only check still reported clean.
    """
    workflow = _workflow()
    assert "scripts/scan_artifacts.py" in workflow, (
        "the packaging job does not run the artifact content scanner"
    )


def test_artifact_scanner_flags_credentials_and_foreign_home_paths():
    """The scanner's own contract, exercised directly.

    The literals are assembled at runtime rather than written out, because this
    file ships in the sdist and the scanner reads it: spelling a credential
    here verbatim would make a clean tree fail its own gate. Widening the
    allowlist to excuse them would blunt the scanner instead.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import scan_artifacts

    aws = "AKIA" + "JKLMNOPQRSTUVWXY"
    gh = "ghp_" + "a" * 36
    openai = "sk-" + "b" * 40
    pem = "-----BEGIN " + "RSA PRIVATE KEY-----"
    assigned = 'api_key = "' + "c" * 24 + '"'
    home_mac = "/Users/" + "alice/work/thing"
    home_linux = "/home/" + "bob/src"

    cases = [
        (f'AWS_KEY = "{aws}"', "aws-access-key"),
        (f'T = "{gh}"', "github-token"),
        (f'K = "{openai}"', "openai-key"),
        (pem, "private-key-block"),
        (assigned, "assigned-secret"),
        (f"path = {home_mac}", "developer-home-path"),
        (f"path = {home_linux}", "developer-home-path"),
    ]
    for text, expected in cases:
        findings = scan_artifacts.scan_text("f.py", text)
        assert any(expected in f for f in findings), (
            f"scanner missed {expected} in {text!r}"
        )


def test_artifact_scanner_allows_declared_synthetic_fixtures():
    """The fixtures that prove secrets don't leak must not trip the scanner.

    Otherwise the only way to a green gate is deleting the tests that protect
    the thing the gate exists for.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import scan_artifacts

    victim = "/Users/" + "victim/.claude/projects/LEAKED.jsonl"
    payload = "/Users/" + "u/.claude/projects/p/session.jsonl"
    windows = "C:\\\\Users\\\\test\\\\AppData"
    aws_example = "AKIA" + "IOSFODNN7EXAMPLE"

    for text in [
        f'"{victim}"',
        f'"transcript_path": "{payload}"',
        f'os.environ["APPDATA"] = "{windows}"',
        f'"my aws key is {aws_example}"',
    ]:
        assert scan_artifacts.scan_text("t.py", text) == [], (
            f"scanner flagged a declared synthetic fixture: {text!r}"
        )


def test_artifact_scanner_flags_windows_home_paths_in_either_spelling():
    r"""A Windows developer path must fail the gate however it is spelled.

    The pattern once required *two* backslashes, so it saw such a path only
    after Python source escaping doubled it. The single-backslash form — what
    a path looks like on disk, in a log, or in a config file — matched
    nothing, and the wheel shipped with the gate reporting clean. Drive letter
    and case are also free: nothing makes one drive more revealing than
    another.

    The paths themselves are assembled below rather than written out: this
    file ships in the sdist and is scanned by the very gate under test.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import scan_artifacts

    # Assembled at runtime: this file ships in the sdist and is scanned by the
    # gate, so a literal foreign home path here would fail the clean-tree test.
    # The separator is split from "Users" for the same reason — with the two
    # joined, the source itself reads as a Windows home path.
    bs = chr(92)
    users = "Users"
    user = "alice"
    variants = [
        ("single backslash", f"C:{bs}{users}{bs}{user}"),
        ("double backslash", f"C:{bs*2}{users}{bs*2}{user}"),
        ("lowercase drive", f"c:{bs}{users}{bs}{user}"),
        ("other drive letter", f"D:{bs}{users}{bs}{user}"),
    ]
    for label, path in variants:
        findings = scan_artifacts.scan_text("f.py", f"CONFIG = {path}")
        assert any("developer-home-path" in f for f in findings), (
            f"scanner missed a Windows home path ({label}): {path!r}"
        )


def test_allowlist_does_not_excuse_paths_that_merely_share_a_prefix():
    """An allowlisted fixture must excuse itself and nothing longer.

    Matching was `startswith`, so every declared fixture opened a family of
    real paths: the one-letter payload fixture excused any home starting with
    that letter, the log-hygiene fixture excused any name extending it, and
    the Windows fixture excused longer user names on the same drive. Each of
    those is a genuine developer home the release gate exists to catch.

    As above, the paths are built at runtime so this file stays clean under
    its own scanner.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import scan_artifacts

    # Split at the segment boundary for the same reason as the test above:
    # written whole, these lines would be real home paths in a shipped file.
    bs = chr(92)
    u = "/Users/"
    collisions = [
        u + "ubuntu",
        u + "user",
        u + "umar",
        u + "victim" + "-corp",
        u + "victim" + "ize",
        f"C:{bs}" + "Users" + f"{bs}" + "test" + "user",
    ]
    for path in collisions:
        findings = scan_artifacts.scan_text("f.py", f"HOME = {path}")
        assert any("developer-home-path" in f for f in findings), (
            f"allowlist prefix leaked a real developer path: {path!r}"
        )

    # The declared fixtures themselves must still pass, or the tests that
    # prove secrets don't leak would have to be deleted to get a green gate.
    fixtures = [u + "victim", u + "u", f"C:{bs}" + "Users" + f"{bs}" + "test"]
    for path in fixtures:
        assert scan_artifacts.scan_text("t.py", f'P = "{path}"') == [], (
            f"tightening the allowlist broke a declared fixture: {path!r}"
        )


def test_a_clean_tree_passes_its_own_artifact_scan():
    """The gate must not fail on the repository it is meant to protect.

    Guards against a test fixture spelling a credential verbatim: this file
    ships in the sdist, so a literal here would make every clean build fail.
    """
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import scan_artifacts

    findings = []
    for path in sorted((REPO_ROOT / "tests").glob("*.py")):
        findings.extend(scan_artifacts.scan_text(path.name, path.read_text()))
    for path in sorted((REPO_ROOT / "voice_buddy").glob("*.py")):
        findings.extend(scan_artifacts.scan_text(path.name, path.read_text()))
    assert not findings, (
        "the repository's own sources trip the artifact scanner:\n  "
        + "\n  ".join(findings)
    )

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
