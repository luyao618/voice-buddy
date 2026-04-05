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

    The transcript is Claude Code's JSONL format where each line is:
      {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "..."}]}}
    Content can be a list of blocks (with "text" type) or a plain string.
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

                    # Claude Code transcript format: type="assistant", message={role, content}
                    if entry.get("type") == "assistant":
                        msg = entry.get("message", {})
                        if isinstance(msg, dict):
                            content = msg.get("content", "")
                            text = _extract_text(content)
                            if text:
                                last_assistant_msg = text

                    # Also support simple JSONL format: {"role": "assistant", "content": "..."}
                    elif entry.get("role") == "assistant":
                        content = entry.get("content", "")
                        text = _extract_text(content)
                        if text:
                            last_assistant_msg = text

                except json.JSONDecodeError:
                    continue
        return last_assistant_msg
    except (FileNotFoundError, OSError):
        return None


def _extract_text(content) -> Optional[str]:
    """Extract text from content which may be a string or a list of blocks."""
    if isinstance(content, str) and content.strip():
        return content.strip()
    elif isinstance(content, list):
        # Content blocks: [{"type": "text", "text": "..."}, ...]
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text", "")
                if t.strip():
                    texts.append(t.strip())
        return "\n".join(texts) if texts else None
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
    """Handle Stop event: check transcript, block + inject additionalContext if task completed."""
    from voice_buddy.main import _debug

    transcript_path = data.get("transcript_path", "")
    if not transcript_path:
        _debug("  injector: no transcript_path")
        return

    message = extract_last_assistant_message(transcript_path)
    if message is None:
        _debug(f"  injector: no assistant message found in {transcript_path}")
        return

    _debug(f"  injector: last assistant msg (first 100 chars): {message[:100]}")

    if not _should_trigger(message):
        _debug(f"  injector: _should_trigger returned False")
        return

    _debug(f"  injector: TRIGGERED! Outputting block + additionalContext")

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

    json_out = json.dumps(output, ensure_ascii=False)
    _debug(f"  injector: stdout JSON: {json_out[:200]}")
    print(json_out)
