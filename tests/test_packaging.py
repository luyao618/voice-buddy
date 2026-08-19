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
import re
import sys
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # Python 3.10 -> dev-only backport
    import tomli as tomllib

REPO_ROOT = Path(__file__).parent.parent

SUPPORTED_MINORS = [10, 11, 12, 13, 14]


def _manifest():
    with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def _canon(name):
    """Canonical distribution name: case- and separator-insensitive.

    PyPI treats `pip_audit` and `pip-audit` as the same project, and pip freeze
    may emit either form, so comparisons normalize both sides.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


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
        _canon(r.name): (str(r.specifier), str(r.marker or ""))
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


def test_requires_python_encodes_both_floor_and_ceiling():
    """requires-python must bound the matrix on BOTH ends.

    A bare ">=3.10" lets any future interpreter resolve as if it were
    certified. 3.15 does not exist yet, so it cannot have been tested — and
    pyobjc in particular tracks the CPython C-ABI, so a new minor is exactly
    where this package would break. The cap makes an untested interpreter fail
    at resolve time with a clear message instead of installing and failing
    later at runtime.

    Asserted through the specifier rather than by string equality, so an
    equivalent-but-differently-spelled range still passes while a genuinely
    wrong bound fails.
    """
    spec = SpecifierSet(_manifest()["project"]["requires-python"])

    floor, ceiling = min(SUPPORTED_MINORS), max(SUPPORTED_MINORS)

    # Every supported version is admitted, including both endpoints.
    for minor in SUPPORTED_MINORS:
        assert spec.contains(f"3.{minor}"), (
            f"3.{minor} is in the supported matrix but requires-python "
            f"({spec}) rejects it"
        )
        # Patch releases of a supported minor must be admitted too: a cap
        # written as "<=3.14" would admit 3.14 but reject 3.14.1.
        assert spec.contains(f"3.{minor}.7"), (
            f"requires-python ({spec}) rejects patch releases of 3.{minor}"
        )

    # Below the floor and above the ceiling are both excluded.
    assert not spec.contains(f"3.{floor - 1}"), (
        f"requires-python ({spec}) admits 3.{floor - 1}, below the floor"
    )
    assert not spec.contains(f"3.{ceiling + 1}"), (
        f"requires-python ({spec}) admits 3.{ceiling + 1}, which is outside "
        f"the tested matrix {SUPPORTED_MINORS}. Add the version to "
        f"SUPPORTED_MINORS and run the suite on it before raising the cap."
    )


def test_requires_python_rejects_the_next_uncertified_minor():
    """The 3.15 rejection the review asked for, stated as install behavior.

    This is what a user hits: resolving on an interpreter above the ceiling
    fails with the same message pip prints, rather than installing a package
    that was never run on that version.
    """
    spec = SpecifierSet(_manifest()["project"]["requires-python"])
    nxt = f"3.{max(SUPPORTED_MINORS) + 1}"

    assert not spec.contains(nxt)
    assert not spec.contains(f"{nxt}.0")
    # Guard the guard: a ceiling that also broke a supported version would
    # make the assertion above pass for the wrong reason.
    assert spec.contains(f"3.{max(SUPPORTED_MINORS)}")


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
        _canon(Requirement(d).name)
        for d in manifest["dependencies"]
    }
    direct |= {
        _canon(Requirement(d).name)
        for d in manifest["optional-dependencies"]["dev"]
    }
    pinned = {
        _canon(r.name)
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
        declared[_canon(req.name)] = req.specifier

    for req in _parse_requirements(REPO_ROOT / "constraints.txt"):
        name = _canon(req.name)
        if name not in declared:
            continue  # transitive pin, no declared range to honor
        version = str(req.specifier).lstrip("=")
        assert declared[name].contains(version), (
            f"constraints.txt pins {name}=={version}, outside declared "
            f"range {declared[name]}"
        )


def test_constraints_are_a_closed_dependency_set():
    """Every pinned package's own requirements must also be pinned.

    The earlier checks only proved that the lines present were exact and that
    *direct* deps appeared. Deleting a transitive pin such as `yarl` still
    passed. This walks the closure: for each pinned distribution installed in
    the current environment, every runtime requirement it declares must itself
    appear in constraints.txt. That makes "fully pinned" a property the test
    enforces rather than a claim about how the file was produced.

    Requirements guarded by an extra (`; extra == "socks"`) are optional and
    only installed on demand, so they are not part of this closure.
    """
    import importlib.metadata as md

    pinned = {_canon(r.name) for r in _parse_requirements(REPO_ROOT / "constraints.txt")}
    assert pinned, "constraints.txt declares no pins"

    # Installer plumbing is deliberately excluded from the artifact.
    ignored = {"pip", "setuptools", "wheel", "voice-buddy"}

    missing = {}
    for name in sorted(pinned):
        try:
            dist = md.distribution(name)
        except md.PackageNotFoundError:
            # Marker-gated pin not installed on this interpreter/platform
            # (e.g. tomli on 3.11+). Nothing to expand.
            continue
        for raw in dist.requires or []:
            req = Requirement(raw)
            if req.marker is not None:
                # Skip extras-only deps; evaluate real environment markers.
                if "extra" in str(req.marker):
                    continue
                if not req.marker.evaluate():
                    continue
            dep = _canon(req.name)
            if dep in ignored or dep in pinned:
                continue
            missing.setdefault(dep, []).append(name)

    assert not missing, (
        "constraints.txt is not a closed set — these dependencies are required "
        f"by pinned packages but are not themselves pinned: "
        f"{ {k: sorted(v) for k, v in missing.items()} }"
    )


def test_constraints_are_free_of_installer_plumbing():
    """pip/setuptools/wheel are the installer, not application dependencies.

    Pinning them here would fight the bootstrap in regen-constraints.sh.
    """
    pinned = {_canon(r.name) for r in _parse_requirements(REPO_ROOT / "constraints.txt")}
    assert not (pinned & {"pip", "setuptools", "wheel"})


def test_regen_script_targets_the_declared_floor():
    """The generator must resolve on the floor, not merely on a supported version.

    aiohttp and pytest gate transitives behind `python_version < "3.11"`. A
    resolve on a newer interpreter drops them, producing constraints that
    install everywhere except the floor — the one version they certify. The
    script hardcodes FLOOR_MINOR, so it can drift from requires-python; this
    ties the two together.
    """
    script = (REPO_ROOT / "scripts" / "regen-constraints.sh").read_text()
    match = re.search(r"^FLOOR_MINOR=(\d+)$", script, re.MULTILINE)
    assert match, "regen-constraints.sh no longer declares FLOOR_MINOR"
    declared_floor = int(match.group(1))
    assert declared_floor == min(SUPPORTED_MINORS)

    # The script's floor must be the same boundary requires-python enforces:
    # admitted itself, and the version below it rejected. Compared by behavior
    # rather than string equality so the ceiling can change independently.
    spec = SpecifierSet(_manifest()["project"]["requires-python"])
    assert spec.contains(f"3.{declared_floor}")
    assert not spec.contains(f"3.{declared_floor - 1}")


def test_floor_gated_transitives_are_pinned():
    """Guards the exact regression that shipped: a closure frozen off-floor.

    These two are required only on 3.10 (`python_version < "3.11"`). They are
    absent from a resolve performed on 3.11+, and their absence is invisible on
    every interpreter except the floor. Asserting them by name means the gap is
    caught by any run of the suite, not only a run that happens to be on 3.10.
    """
    pinned = {_canon(r.name) for r in _parse_requirements(REPO_ROOT / "constraints.txt")}
    for name in ("async-timeout", "exceptiongroup", "tomli"):
        assert name in pinned, (
            f"{name} is required on the 3.{min(SUPPORTED_MINORS)} floor but is "
            f"not pinned — constraints.txt was likely regenerated on a newer "
            f"interpreter. Re-run: PYTHON=python3.{min(SUPPORTED_MINORS)} "
            f"bash scripts/regen-constraints.sh"
        )
