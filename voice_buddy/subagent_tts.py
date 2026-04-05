"""Standalone TTS script for the voice-buddy subagent's SubagentStop hook.

Reads stdin JSON, extracts last assistant message from agent_transcript_path,
synthesizes speech, and plays audio.

This script is invoked by the subagent's hook, NOT by the main hook entry point.
"""

import json
import sys

from voice_buddy.injector import extract_last_assistant_message
from voice_buddy.tts import synthesize_to_file
from voice_buddy.player import play_audio


def main() -> None:
    """Read subagent transcript and speak the generated message."""
    try:
        stdin_content = sys.stdin.read().strip()
        if not stdin_content:
            sys.exit(0)

        data = json.loads(stdin_content)

        # Use agent_transcript_path (NOT transcript_path, which is parent session)
        transcript_path = data.get("agent_transcript_path")
        if not transcript_path:
            sys.exit(0)

        message = extract_last_assistant_message(transcript_path)
        if not message:
            sys.exit(0)

        audio_path = synthesize_to_file(message)
        if audio_path is None:
            sys.exit(0)

        play_audio(audio_path)
        sys.exit(0)

    except Exception as e:
        print(f"subagent_tts error: {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
