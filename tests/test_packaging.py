# tests/test_packaging.py
"""Packaging metadata and supported-Python-matrix contracts.

The matrix here is empirical, not aspirational: 3.10-3.14 were each installed
with the current dependency set and ran the full suite green. 3.9 fails because
pyobjc-core publishes no 3.9 wheel and its source build fails, and because
pytest 9.x / pip 26.x both declare Requires-Python >=3.10.
"""
import sys
from pathlib import Path

import pytest

# tomllib landed in 3.11, but the supported floor is 3.10, so the parser has to
# be optional or this module would fail on the very version it certifies.
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = None

REPO_ROOT = Path(__file__).parent.parent

SUPPORTED_MINORS = [10, 11, 12, 13, 14]

requires_toml = pytest.mark.skipif(
    tomllib is None, reason="tomllib requires Python 3.11+"
)


def _manifest():
    with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


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


@requires_toml
def test_requires_python_floor_is_3_10():
    assert _manifest()["project"]["requires-python"] == ">=3.10"


@requires_toml
def test_classifiers_match_supported_matrix():
    classifiers = _manifest()["project"]["classifiers"]
    declared = {
        c.rsplit(" :: ", 1)[-1]
        for c in classifiers
        if c.startswith("Programming Language :: Python :: 3.")
    }
    assert declared == {f"3.{m}" for m in SUPPORTED_MINORS}


@requires_toml
def test_runtime_dependencies_are_bounded():
    # An unbounded dependency lets a breaking major land silently on install.
    for dep in _manifest()["project"]["dependencies"]:
        assert "<" in dep, f"Unbounded runtime dependency: {dep}"


@requires_toml
def test_quartz_cap_admits_current_release():
    # The old "<12.0" cap pinned Quartz at 11.1 while pyobjc-core resolved to
    # 12.x. Guard against the cap being re-tightened below the verified 12.2.1.
    quartz = [
        d for d in _manifest()["project"]["dependencies"] if "Quartz" in d
    ]
    assert len(quartz) == 1
    assert "<12.0" not in quartz[0]


@requires_toml
def test_requirements_files_mirror_pyproject():
    # Two installers must not drift apart on the version ranges they allow.
    runtime = (REPO_ROOT / "requirements.txt").read_text()
    for dep in _manifest()["project"]["dependencies"]:
        spec = dep.split(";")[0].strip()
        assert spec in runtime, f"requirements.txt missing/differs on: {spec}"


def test_dev_requirements_reuse_runtime_file():
    # Avoids re-declaring runtime deps in a second place where they can drift.
    assert "-r requirements.txt" in (
        REPO_ROOT / "requirements-dev.txt"
    ).read_text()


@requires_toml
def test_console_script_entry_point_resolves():
    entry = _manifest()["project"]["scripts"]["voice-buddy"]
    module_path, func_name = entry.split(":")
    import importlib

    module = importlib.import_module(module_path)
    assert callable(getattr(module, func_name))
