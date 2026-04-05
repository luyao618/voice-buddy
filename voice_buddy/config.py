"""Load configuration and templates from JSON files."""

import json
from pathlib import Path

_ROOT_DIR = Path(__file__).parent.parent


def load_config() -> dict:
    """Load buddy-config.json from the project root."""
    config_path = _ROOT_DIR / "buddy-config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_templates() -> dict:
    """Load templates.json from the project root."""
    templates_path = _ROOT_DIR / "templates.json"
    with open(templates_path, "r", encoding="utf-8") as f:
        return json.load(f)
