"""Text-to-speech synthesis using edge-tts."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from typing import Optional


async def _synthesize(text: str, voice: str, rate: str, pitch: str, output_path: str) -> None:
    """Run edge-tts synthesis asynchronously."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def synthesize_to_file(
    text: str,
    voice: str = "zh-CN-XiaoyiNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz",
) -> Optional[str]:
    """Synchronous wrapper: synthesize text and return temp file path, or None on error."""
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_synthesize(text, voice, rate, pitch, tmp.name))
        finally:
            loop.close()

        # Schedule cleanup after 30 seconds
        _schedule_cleanup(tmp.name, delay=30)
        return tmp.name
    except Exception as e:
        print(f"TTS synthesis failed: {e}", file=sys.stderr)
        return None


def _schedule_cleanup(file_path: str, delay: int = 30) -> None:
    """Delete temp file after a delay, in a background thread.

    The thread is daemon=True so it won't block process exit. If the process
    exits early, the temp file is orphaned — acceptable since the OS /tmp
    cleaner will eventually reclaim it, and deleting too early would break
    playback (the audio player subprocess has the file open).
    """
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
