#!/usr/bin/env bash
# Regenerate constraints.txt from a clean resolve of the ranges in pyproject.toml.
#
#   bash scripts/regen-constraints.sh [python]
#
# Uses only the interpreter's own stdlib `venv` + the pip it bootstraps, so it
# runs on a fresh clone with no extra tooling. Set PYTHON=... or pass an
# interpreter as $1 to pick one; defaults to python3.
#
# The regenerated file replaces constraints.txt only after every step succeeds:
# the resolve writes to a temp file and is validated before an atomic mv, so a
# resolver failure leaves the committed artifact untouched.
set -euo pipefail

PYTHON="${PYTHON:-${1:-python3}}"
OUT="constraints.txt"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/vb-constraints.XXXXXX")"
TMP_OUT="$(mktemp "${TMPDIR:-/tmp}/vb-constraints-out.XXXXXX")"

cleanup() { rm -rf "$WORK" "$TMP_OUT"; }
trap cleanup EXIT

command -v "$PYTHON" >/dev/null 2>&1 || {
  echo "error: interpreter not found: $PYTHON" >&2
  exit 1
}

echo "==> creating clean venv with $("$PYTHON" --version 2>&1)"
# ensurepip ships with CPython, so this needs no pre-existing pip or uv.
"$PYTHON" -m venv "$WORK"
VPY="$WORK/bin/python"

echo "==> upgrading pip"
"$VPY" -m pip install --quiet --upgrade pip

echo "==> resolving runtime + dev extras"
# No `|| true` here: a resolver or install failure must abort the script (set -e)
# before anything touches the committed constraints file.
"$VPY" -m pip install --quiet ".[dev]"

echo "==> freezing closure"
FROZEN="$WORK/frozen.txt"
# Drop the project itself (a non-editable install is emitted as a local
# `voice-buddy @ file:///...` URL, which would bake this machine's path into a
# committed file) plus installer plumbing.
"$VPY" -m pip freeze --exclude-editable \
  | grep -viE '^(voice-buddy|pip|setuptools|wheel)( |==|@)' \
  | sort -f > "$FROZEN"

# Guard against writing an empty or obviously truncated artifact.
PIN_COUNT="$(grep -c '==' "$FROZEN" || true)"
if [ "$PIN_COUNT" -lt 10 ]; then
  echo "error: refusing to write $OUT — only $PIN_COUNT pins resolved" >&2
  exit 1
fi
for required in edge-tts pytest packaging; do
  grep -qiE "^${required}==" "$FROZEN" || {
    echo "error: refusing to write $OUT — missing expected pin: $required" >&2
    exit 1
  }
done

# A local path or VCS URL would make the artifact machine-specific.
if grep -qE '(@ )?(file://|git\+|https?://|/Users/|/home/)' "$FROZEN"; then
  echo "error: refusing to write $OUT — non-portable entry:" >&2
  grep -nE '(@ )?(file://|git\+|https?://|/Users/|/home/)' "$FROZEN" >&2
  exit 1
fi

{
  echo "# Fully-pinned direct and transitive versions for a reproducible install."
  echo "#"
  echo "# GENERATED FILE — do not hand-edit. Regenerate with:"
  echo "#   bash scripts/regen-constraints.sh"
  echo "#"
  echo "# pyproject.toml is the source of truth for what is ALLOWED (ranges);"
  echo "# this file records what was actually VERIFIED (exact versions)."
  echo "#"
  echo "# Use:"
  echo "#   pip install -c constraints.txt .            # runtime"
  echo "#   pip install -c constraints.txt -e '.[dev]'  # development"
  echo "#"
  echo "# pip/setuptools/wheel are omitted deliberately: they are the installer,"
  echo "# not part of the application's dependency closure."
  cat "$FROZEN"
} > "$TMP_OUT"

# Atomic replace, and only now that the content is known-good.
mv "$TMP_OUT" "$OUT"
echo "==> wrote $OUT ($PIN_COUNT pins)"
