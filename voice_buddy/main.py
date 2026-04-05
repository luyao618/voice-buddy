"""Hook entry point: read stdin JSON, dispatch by event type."""

import json
import sys

from voice_buddy.context import analyze_context
from voice_buddy.response import select_response
from voice_buddy.tts import synthesize_to_file
from voice_buddy.player import play_audio


def handle_hook_event(data: dict) -> None:
    """Process a hook event: analyze, generate response, speak."""
    event_name = data.get("hook_event_name", "")

    # Stop event: try subagent path (block + additionalContext)
    if event_name == "Stop":
        handle_stop_event(data)
        return

    # All other events: context -> response -> tts -> play
    ctx = analyze_context(data)
    if ctx is None:
        return  # Event filtered out, stay silent

    text = select_response(ctx)
    if text is None:
        return  # No matching template, stay silent

    audio_path = synthesize_to_file(text)
    if audio_path is None:
        return  # TTS failed, stay silent

    play_audio(audio_path)


def handle_stop_event(data: dict) -> None:
    """Handle Stop event: block + inject context to trigger subagent."""
    from voice_buddy.injector import process_stop_event
    process_stop_event(data)


def run() -> None:
    """Main entry point: read stdin, parse JSON, handle event."""
    try:
        stdin_content = sys.stdin.read().strip()
        if not stdin_content:
            sys.exit(0)

        data = json.loads(stdin_content)
        handle_hook_event(data)
        sys.exit(0)

    except json.JSONDecodeError as e:
        print(f"Error parsing JSON input: {e}", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(0)
