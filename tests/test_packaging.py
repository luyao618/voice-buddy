# tests/test_packaging.py
"""Packaging metadata and supported-Python-matrix contracts.

The matrix here is empirical, not aspirational: 3.10-3.14 were each installed
with the current dependency set and ran the full suite green. 3.9 fails because
pyobjc-core publishes no 3.9 wheel and its source build fails, and because
pytest 9.x / pip 26.x both declare Requires-Python >=3.10.

Every contract in this module runs on the 3.10 floor. tomllib is 3.11+, so the
dev extra carries a `tomli` fallback rather than skipping these tests on the
one version they most need to certify.
"""
import sys
from pathlib import Path

from packaging.requirements import Requirement

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.10 -> dev-only backport
    import tomli as tomllib

REPO_ROOT = Path(__file__).parent.parent

SUPPORTED_MINORS = [10, 11, 12, 13, 14]


def _manifest():
    with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def _parse_requirements(path):
    """Parse a requirements file into Requirement objects.

    Skips comments, blanks, and `-r` includes; the include is asserted
    separately so runtime deps stay declared in exactly one place.
    """
    reqs = []
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        reqs.append(Requirement(line))
    return reqs


def _normalize(reqs):
    """Map name -> (specifier, marker), so comparison covers ranges and markers.

    A plain substring check would miss an extra dependency, a widened range, or
    a dropped environment marker, so each field is compared explicitly.
    """
    return {
        r.name.lower().replace("_", "-"): (str(r.specifier), str(r.marker or ""))
        for r in reqs
    }


def test_pyproject_exists():
    assert (REPO_ROOT / "pyproject.toml").exists()


def test_running_interpreter_is_supported():
    # The floor is enforced by requires-python at install time; this asserts the
    # interpreter actually running the suite is inside the documented matrix, so
    # a green run on an unsupported version can't be mistaken for support.
    assert sys.version_info[0] == 3
    assert sys.version_info[1] in SUPPORTED_MINORS, (
        f"Running on 3.{sys.version_info[1]}, which is outside the supported "
        f"matrix {SUPPORTED_MINORS}"
    )


def test_requires_python_floor_is_3_10():
    assert _manifest()["project"]["requires-python"] == ">=3.10"


def test_classifiers_match_supported_matrix():
    classifiers = _manifest()["project"]["classifiers"]
    declared = {
        c.rsplit(" :: ", 1)[-1]
        for c in classifiers
        if c.startswith("Programming Language :: Python :: 3.")
    }
    assert declared == {f"3.{m}" for m in SUPPORTED_MINORS}


def test_runtime_dependencies_are_bounded():
    # An unbounded dependency lets a breaking major land silently on install.
    for dep in _manifest()["project"]["dependencies"]:
        assert Requirement(dep).specifier, f"Unbounded dependency: {dep}"
        assert "<" in dep, f"No upper bound on: {dep}"


def test_quartz_cap_admits_current_release():
    # The old "<12.0" cap pinned Quartz at 11.1 while pyobjc-core resolved to
    # 12.x. Guard against the cap being re-tightened below the verified 12.2.1.
    quartz = [
        Requirement(d)
        for d in _manifest()["project"]["dependencies"]
        if "Quartz" in d
    ]
    assert len(quartz) == 1
    assert quartz[0].specifier.contains("12.2.1")
    # macOS-only dependency must keep its marker, or Linux installs pull pyobjc.
    assert 'sys_platform == "darwin"' in str(quartz[0].marker)


def test_runtime_requirements_match_pyproject_exactly():
    # Bidirectional: catches an extra dep in either file, a widened/narrowed
    # range, and a dropped or added environment marker.
    manifest = _normalize(
        Requirement(d) for d in _manifest()["project"]["dependencies"]
    )
    on_disk = _normalize(_parse_requirements(REPO_ROOT / "requirements.txt"))
    assert on_disk == manifest


def test_dev_requirements_match_pyproject_exactly():
    # The dev extra was previously never compared at all.
    dev_extra = _manifest()["project"]["optional-dependencies"]["dev"]
    manifest = _normalize(Requirement(d) for d in dev_extra)
    on_disk = _normalize(_parse_requirements(REPO_ROOT / "requirements-dev.txt"))
    assert on_disk == manifest


def test_dev_requirements_reuse_runtime_file():
    # Avoids re-declaring runtime deps in a second place where they can drift.
    assert "-r requirements.txt" in (
        REPO_ROOT / "requirements-dev.txt"
    ).read_text()


def test_console_script_entry_point_resolves():
    entry = _manifest()["project"]["scripts"]["voice-buddy"]
    module_path, func_name = entry.split(":")
    import importlib

    module = importlib.import_module(module_path)
    assert callable(getattr(module, func_name))


def test_constraints_file_pins_every_verified_dependency():
    """The constraints artifact must fully pin, not merely bound."""
    constraints = _parse_requirements(REPO_ROOT / "constraints.txt")
    assert constraints, "constraints.txt declares no pins"
    for req in constraints:
        specs = list(req.specifier)
        assert len(specs) == 1 and specs[0].operator == "==", (
            f"{req.name} is not pinned to an exact version: {req.specifier}"
        )


def test_constraints_cover_all_direct_dependencies():
    manifest = _manifest()["project"]
    direct = {
        Requirement(d).name.lower().replace("_", "-")
        for d in manifest["dependencies"]
    }
    direct |= {
        Requirement(d).name.lower().replace("_", "-")
        for d in manifest["optional-dependencies"]["dev"]
    }
    pinned = {
        r.name.lower().replace("_", "-")
        for r in _parse_requirements(REPO_ROOT / "constraints.txt")
    }
    missing = direct - pinned
    assert not missing, f"Direct dependencies absent from constraints: {missing}"


def test_constraints_satisfy_declared_ranges():
    """A pin outside its declared range would make the two files contradict."""
    manifest = _manifest()["project"]
    declared = {}
    for dep in manifest["dependencies"] + manifest["optional-dependencies"]["dev"]:
        req = Requirement(dep)
        declared[req.name.lower().replace("_", "-")] = req.specifier

    for req in _parse_requirements(REPO_ROOT / "constraints.txt"):
        name = req.name.lower().replace("_", "-")
        if name not in declared:
            continue  # transitive pin, no declared range to honor
        version = str(req.specifier).lstrip("=")
        assert declared[name].contains(version), (
            f"constraints.txt pins {name}=={version}, outside declared "
            f"range {declared[name]}"
        )
