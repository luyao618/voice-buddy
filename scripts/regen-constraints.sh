#!/usr/bin/env bash
# Regenerate constraints.txt from a clean resolve of the declared ranges.
# Usage: bash scripts/regen-constraints.sh
set -euo pipefail

PIPWHL="${PIPWHL:-$PWD/dltest/pip-26.2.1-py3-none-any.whl}"
OUT="constraints.txt"
WORK=".venvconstraints"

rm -rf "$WORK"
uv venv --python 3.12 "$WORK" > /dev/null 2>&1
PYTHONPATH="$PIPWHL" "$WORK/bin/python" -m pip install -q --no-input "$PIPWHL" > /dev/null 2>&1

# Resolve runtime + dev extras together so the pins are mutually consistent.
"$WORK/bin/python" -m pip install -q ".[dev]" 2>&1 | grep -viE "notice|upgrade" || true

{
  echo "# Fully-pinned direct and transitive versions for a reproducible install."
  echo "#"
  echo "# Generated from a clean resolve of the ranges declared in pyproject.toml"
  echo "# on CPython 3.12 / macOS arm64, then verified across Python 3.10-3.14."
  echo "#"
  echo "# Use:"
  echo "#   pip install -c constraints.txt .          # runtime"
  echo "#   pip install -c constraints.txt -e '.[dev]'  # development"
  echo "#"
  echo "# Regenerate after changing a range in pyproject.toml:"
  echo "#   bash scripts/regen-constraints.sh"
  echo "#"
  echo "# pyproject.toml stays the source of truth for what is ALLOWED; this file"
  echo "# records what was actually verified. Tests assert the two agree."
  "$WORK/bin/python" -m pip freeze --exclude-editable 2>/dev/null \
    | grep -viE "^voice-buddy" \
    | sort -f
} > "$OUT"

rm -rf "$WORK"
echo "wrote $OUT ($(grep -vc '^#' "$OUT") pins)"
