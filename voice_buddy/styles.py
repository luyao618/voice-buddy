"""Load style definitions from personas/ directory."""

import json
from pathlib import Path
from typing import Optional

STYLES_DIR = Path(__file__).parent.parent / "personas"


def load_style(style_id: str) -> Optional[dict]:
    """Load a style definition by ID. Returns None if not found."""
    path = STYLES_DIR / f"{style_id}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_styles() -> list[dict]:
    """List all available styles."""
    styles = []
    for path in sorted(STYLES_DIR.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            styles.append(json.load(f))
    return styles
