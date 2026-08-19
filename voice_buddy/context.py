"""Analyze hook event data and extract semantic context."""

from dataclasses import dataclass, field
from typing import Optional


def coerce_text(value) -> str:
    """Return payload text as a string, or "" if it isn't usable text.

    Hook payload fields are documented as strings, but a hook must not crash on
    a payload that disagrees: Claude Code treats a non-zero exit as a hook
    failure and surfaces it to the user. Anything that isn't a string (or a
    content-block list carrying text) is treated as "no text".
    """
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        # Defensive: some producers pass content blocks rather than flat text.
        parts = []
        for block in value:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p.strip())
    return ""


@dataclass
class ContextResult:
    event: str          # "notification", "sessionstart", etc.
    sub_event: str      # "default", etc.
    mood: str = ""      # "happy", "sad", "encouraging", "neutral"
    detail: str = ""    # Human-readable detail string
    variables: dict = field(default_factory=dict)


def analyze_context(data: dict) -> Optional[ContextResult]:
    """Analyze hook stdin JSON and return a ContextResult, or None if silent."""
    if not isinstance(data, dict):
        return None

    event_name = data.get("hook_event_name", "")

    if event_name == "SessionStart":
        return ContextResult(event="sessionstart", sub_event="default", mood="happy")
    elif event_name == "SessionEnd":
        return ContextResult(event="sessionend", sub_event="default", mood="neutral")
    elif event_name == "Notification":
        return _analyze_notification(data)
    else:
        # Stop goes through injector path (block + additionalContext),
        # unknown events are ignored.
        return None


def _analyze_notification(data: dict) -> Optional[ContextResult]:
    """Notification: Claude sent a notification to the user.

    Per the documented payload, `message` carries the notification text and
    `title` is optional; `notification_type` names the variant that fired.
    Both text fields are coerced so a malformed payload degrades to a generic
    notification instead of raising.
    """
    message = coerce_text(data.get("message"))
    title = coerce_text(data.get("title"))

    return ContextResult(
        event="notification",
        sub_event="default",
        mood="encouraging",
        detail=(message or title)[:200],
    )
