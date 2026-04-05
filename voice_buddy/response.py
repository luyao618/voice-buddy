"""Select template responses and perform variable substitution."""

import random
from typing import Optional

from voice_buddy.config import load_templates
from voice_buddy.context import ContextResult


def select_response(ctx: ContextResult) -> Optional[str]:
    """Select a random template response for the given context.

    Returns None if no matching template is found.
    """
    templates = load_templates()

    event_templates = templates.get(ctx.event)
    if event_templates is None:
        return None

    candidates = event_templates.get(ctx.sub_event)
    if candidates is None or len(candidates) == 0:
        return None

    text = random.choice(candidates)

    # Variable substitution: replace {{key}} with values from ctx.variables
    if ctx.variables:
        for key, value in ctx.variables.items():
            text = text.replace("{{" + key + "}}", str(value))

    return text
