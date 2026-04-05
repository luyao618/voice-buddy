"""Stop event handler: read transcript, check trigger criteria, block + inject additionalContext."""

import json
import re
import sys
from typing import Optional


# Completion signal keywords (English)
_COMPLETION_EN = re.compile(
    r"\b(?:done|complete[d]?|finish(?:ed)?|implement(?:ed)?|fix(?:ed)?|"
    r"creat(?:ed|e)|refactor(?:ed)?|update[d]?|built|resolved|added)\b",
    re.IGNORECASE,
)

# Completion signal keywords (Chinese)
_COMPLETION_ZH = re.compile(r"(?:完成|修复|实现|搞定|创建|更新|添加|重构)")

# File modification signals
_FILE_MOD = re.compile(
    r"(?:wrote\s+to|created?\s+file|updated?\s+(?:the\s+)?(?:file|test)|"
    r"modified|changed\s+\d+\s+file)",
    re.IGNORECASE,
)


def extract_last_assistant_message(transcript_path: str) -> Optional[str]:
    """Read transcript file and extract the last assistant message.

    The transcript is expected to be JSONL format with {role, content} objects.
    """
    try:
        last_assistant_msg = None
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("role") == "assistant":
                        content = entry.get("content", "")
                        if isinstance(content, str) and content.strip():
                            last_assistant_msg = content.strip()
                except json.JSONDecodeError:
                    continue
        return last_assistant_msg
    except (FileNotFoundError, OSError):
        return None


def _should_trigger(message: str) -> bool:
    """Check if the message indicates a substantive task was completed.

    At least one semantic signal must be present:
    - Completion keywords (English or Chinese)
    - File modification signals
    """
    if _COMPLETION_EN.search(message):
        return True
    if _COMPLETION_ZH.search(message):
        return True
    if _FILE_MOD.search(message):
        return True
    return False


def process_stop_event(data: dict) -> None:
    """Handle Stop event: check transcript, block + inject additionalContext if task completed.

    When a substantive task is detected:
    - Outputs decision "block" to prevent Claude from stopping
    - Injects additionalContext prompting Claude to call the voice-buddy subagent
    - Claude continues, calls subagent, subagent generates a voice response
    - On the next Stop attempt, the transcript has changed (subagent call result),
      so _should_trigger won't match again — Claude stops normally.

    When no task is detected, outputs nothing — Claude stops normally.
    """
    transcript_path = data.get("transcript_path", "")
    if not transcript_path:
        return

    message = extract_last_assistant_message(transcript_path)
    if message is None:
        return

    if not _should_trigger(message):
        return

    # Truncate message for context injection (keep it concise)
    summary = message[:500] if len(message) > 500 else message

    output = {
        "decision": "block",
        "reason": "Voice Buddy is generating a voice response",
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": (
                f"[Voice Buddy] A task was just completed. Summary: {summary}\n\n"
                f"Please call the voice-buddy agent to generate a short, "
                f"personality-driven voice response about this completion."
            ),
        },
    }

    print(json.dumps(output, ensure_ascii=False))
