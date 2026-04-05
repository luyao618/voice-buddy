"""Text-to-speech synthesis using edge-tts."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from voice_buddy.config import load_config


async def _synthesize(text: str, output_path: str) -> None:
    """Run edge-tts synthesis asynchronously."""
    import edge_tts

    config = load_config()
    tts_config = config["tts"]

    communicate = edge_tts.Communicate(
        text,
        voice=tts_config["voice"],
        rate=tts_config["rate"],
        pitch=tts_config["pitch"],
    )
    await communicate.save(output_path)


def synthesize_to_file(text: str) -> str | None:
    """Synthesize text to a temporary audio file.

    Returns the path to the generated .mp3 file, or None on failure.
    The caller is responsible for cleanup, but since playback is async
    (Popen with start_new_session), we schedule cleanup after a delay.
    """
    try:
        # Create a temp file that won't be auto-deleted (async playback needs it)
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp_path = tmp.name
        tmp.close()

        asyncio.run(_synthesize(text, tmp_path))

        # Schedule cleanup after 30 seconds (enough for playback to finish)
        _schedule_cleanup(tmp_path, delay=30)

        return tmp_path
    except Exception as e:
        print(f"TTS synthesis failed: {e}", file=sys.stderr)
        return None


def _schedule_cleanup(file_path: str, delay: int = 30) -> None:
    """Delete temp file after a delay, in a background thread."""
    import threading

    def _cleanup():
        import time
        time.sleep(delay)
        try:
            os.remove(file_path)
        except OSError:
            pass

    t = threading.Thread(target=_cleanup, daemon=True)
    t.start()
