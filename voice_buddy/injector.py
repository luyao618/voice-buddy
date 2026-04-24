"""Stop event handler: read transcript, check trigger criteria, block + inject additionalContext."""

import json
import os
import re
import sys
from typing import Optional


# Completion signal keywords (English)
# Use word boundaries to reduce false positives (e.g. "not done yet" still
# matches "done", but that's acceptable — the alternative of NLU is too heavy).
_COMPLETION_EN = re.compile(
    r"\b(?:done|completed?|finish(?:ed)?|implement(?:ed)?|fix(?:ed)?|"
    r"created?|refactored?|updated?|built|resolved|added)\b",
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


def process_stop_event(data: dict, user_config: dict = None) -> None:
    """Handle Stop event: block via exit code 2 to trigger subagent.

    Exit code 2 prevents Claude from stopping and feeds stderr back to Claude.
    We output JSON with decision=block and style-aware additionalContext so
    Claude knows to call the voice-buddy subagent.
    """
    if user_config is None:
        from voice_buddy.config import load_user_config
        user_config = load_user_config()

    # Guard: don't re-trigger if we're already inside a stop-hook retry.
    # Claude Code sets stop_hook_active=true on the second invocation to
    # prevent infinite blocking loops.
    if data.get("stop_hook_active"):
        return

    # Prefer last_assistant_message from hook input (reliable, no race condition).
    # Fall back to reading transcript file (for older Claude Code versions).
    message = data.get("last_assistant_message")
    if not message:
        transcript_path = data.get("transcript_path", "")
        if not transcript_path:
            return
        message = extract_last_assistant_message(transcript_path)
        if message is None:
            return

    if not _should_trigger(message):
        return

    # Build style-aware context for stderr
    style_id = user_config.get("style", "cute-girl")
    nickname = user_config.get("nickname", "Master")
    persona_override = user_config.get("persona_override")

    from voice_buddy.styles import load_style
    from voice_buddy.config import get_repo_root
    style = load_style(style_id)
    agent_name = style["agent"] if style else "voice-buddy-cute-girl"

    # Resolve actual plugin root path at runtime (CLAUDE_PLUGIN_ROOT may not
    # be available in agent's Bash env, so we bake in the absolute path).
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", str(get_repo_root()))

    summary = message[:150] if len(message) > 150 else message

    persona_line = ""
    if persona_override:
        persona_line = f"Persona override: {persona_override}\n"

    # Exit code 2: Claude Code blocks the stop and feeds stderr back to Claude.
    # Instruct Claude to call the style-specific agent, then TTS.
    print(
        f"REQUIRED ACTION — Voice Buddy ({style_id}):\n"
        f"Nickname: {nickname}\n"
        f"{persona_line}"
        f"Task summary: {summary}\n\n"
        f"Generate a {style_id} style one-sentence summary addressing the user as {nickname}, "
        f"then call Bash to speak it:\n"
        f"PYTHONPATH={plugin_root} python3 -m voice_buddy.subagent_tts '<your sentence>'",
        file=sys.stderr,
    )
    sys.exit(2)
