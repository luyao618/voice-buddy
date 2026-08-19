"""Offline stub for `edge_tts`, used only by the subprocess entry-point tests.

`test_hook_entrypoint.py` spawns `python -m voice_buddy` for real, so it cannot
patch the TTS backend in-process. Without this stub the Notification cases reach
`edge_tts.Communicate(...).save()`, which performs a live network request: the
contract assertions then depend on the machine having `edge-tts` installed and
being online, and fail with "TTS synthesis failed: No module named 'edge_tts'"
on stderr.

Shadowing the module keeps the whole voice_buddy code path under test and
removes only the network call.
"""

from __future__ import annotations


class Communicate:
    """Minimal stand-in for `edge_tts.Communicate`.

    Mirrors only the surface `voice_buddy.tts` uses: construction with the
    voice/rate/pitch parameters, then an awaitable `save(path)`.
    """

    def __init__(self, text, voice, rate="+0%", pitch="+0Hz", **kwargs):
        self.text = text
        self.voice = voice
        self.rate = rate
        self.pitch = pitch

    async def save(self, output_path: str) -> None:
        # A non-empty file is enough: the caller only checks it exists before
        # handing the path to the audio player.
        with open(output_path, "wb") as f:
            f.write(b"\x00")
