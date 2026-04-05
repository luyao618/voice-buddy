"""Cross-platform audio playback.

Detection priority:
  macOS:   afplay (built-in)
  Linux:   paplay -> aplay -> ffplay -> mpg123
  Windows: winsound

Playback is asynchronous (subprocess.Popen with start_new_session=True)
so the hook script exits immediately without waiting for audio to finish.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

try:
    import winsound  # type: ignore[import-not-found]
except ImportError:
    winsound = None  # type: ignore[assignment]


def get_audio_player() -> list[str] | None:
    """Detect the appropriate audio player for the current platform.

    Returns a list of [command, *args] or None if no player is found.
    """
    system = platform.system()

    if system == "Darwin":
        return ["afplay"]
    elif system == "Linux":
        players = [
            ["paplay"],
            ["aplay"],
            ["ffplay", "-nodisp", "-autoexit"],
            ["mpg123", "-q"],
        ]
        for player in players:
            try:
                subprocess.run(
                    ["which", player[0]],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )
                return player
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
        return None
    elif system == "Windows":
        return ["WINDOWS"]
    else:
        return None


def play_audio(file_path: str | Path) -> bool:
    """Play an audio file asynchronously.

    Returns True if playback was initiated, False otherwise.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        print(f"Audio file not found: {file_path}", file=sys.stderr)
        return False

    audio_player = get_audio_player()
    if audio_player is None:
        print("No audio player found", file=sys.stderr)
        return False

    try:
        if audio_player[0] == "WINDOWS":
            if winsound is not None:
                winsound.PlaySound(
                    str(file_path),
                    winsound.SND_FILENAME | winsound.SND_NODEFAULT,
                )
                return True
            return False
        else:
            subprocess.Popen(
                audio_player + [str(file_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return True
    except (FileNotFoundError, OSError) as e:
        print(f"Error playing audio: {e}", file=sys.stderr)
        return False
