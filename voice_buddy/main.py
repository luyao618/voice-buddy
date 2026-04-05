"""Hook entry point: read stdin JSON, dispatch by event type."""

import json
import sys
import os
from datetime import datetime

_DEBUG_LOG = os.path.expanduser("~/voice-buddy-debug.log")


def _debug(msg: str) -> None:
    """Append a debug message to the log file."""
    try:
        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except Exception:
        pass


from voice_buddy.context import analyze_context
from voice_buddy.response import select_response
from voice_buddy.tts import synthesize_to_file
from voice_buddy.player import play_audio


def handle_hook_event(data: dict) -> None:
    """Process a hook event: analyze, generate response, speak."""
    event_name = data.get("hook_event_name", "")
    _debug(f"EVENT: {event_name}")

    # Stop event: try subagent path (block + additionalContext)
    if event_name == "Stop":
        _debug(f"Stop event received. transcript_path={data.get('transcript_path', 'MISSING')}")
        handle_stop_event(data)
        return

    # All other events: context -> response -> tts -> play
    ctx = analyze_context(data)
    if ctx is None:
        _debug(f"  context returned None, staying silent")
        return

    _debug(f"  context: event={ctx.event} sub_event={ctx.sub_event}")
    text = select_response(ctx)
    if text is None:
        _debug(f"  no template match, staying silent")
        return

    _debug(f"  response: {text}")
    audio_path = synthesize_to_file(text)
    if audio_path is None:
        _debug(f"  TTS failed")
        return

    _debug(f"  playing: {audio_path}")
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
