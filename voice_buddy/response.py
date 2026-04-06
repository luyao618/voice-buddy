"""Select a response template for a given context and style."""

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Events that have pre-packaged audio (no nickname substitution)
_PREPACKAGED_EVENTS = {"sessionstart", "sessionend"}


@dataclass
class ResponseResult:
    text: str                       # The final text (after substitution)
    audio_id: Optional[str]         # e.g. "sessionstart_03" for pre-packaged, None for real-time TTS


def _load_style_templates(style: str) -> Optional[dict]:
    """Load templates for a given style."""
    path = _TEMPLATES_DIR / f"{style}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def select_response(
    ctx,
    style: str = "cute-girl",
    nickname: str = "Master",
) -> Optional[ResponseResult]:
    """Select a response for the given context and style.

    Returns ResponseResult with text and optional audio_id, or None if silent.
    """
    templates = _load_style_templates(style)
    if templates is None:
        return None

    candidates = templates.get(ctx.event)
    if not candidates:
        return None

    index = random.randrange(len(candidates))
    text = candidates[index]

    # Substitute nickname for notification events
    text = text.replace("{{nickname}}", nickname)

    # Pre-packaged events get an audio_id for file lookup
    audio_id = None
    if ctx.event in _PREPACKAGED_EVENTS:
        audio_id = f"{ctx.event}_{index + 1:02d}"

    return ResponseResult(text=text, audio_id=audio_id)
