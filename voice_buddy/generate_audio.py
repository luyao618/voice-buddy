"""Generate pre-packaged audio files from templates and style configs.

Usage: python3 -m voice_buddy.generate_audio
"""

import asyncio
import json
from pathlib import Path

from voice_buddy.styles import load_style, list_styles, STYLES_DIR

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
ASSETS_DIR = Path(__file__).parent.parent / "assets" / "audio"

# Only these events get pre-packaged audio (no nickname substitution)
PREPACKAGED_EVENTS = ["sessionstart", "sessionend"]


async def generate_one(text: str, voice: str, rate: str, pitch: str, output_path: str) -> None:
    """Generate a single MP3 file."""
    import edge_tts
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def generate_all() -> None:
    """Generate all pre-packaged audio files for all styles."""
    styles = list_styles()

    for style in styles:
        style_id = style["id"]
        tts = style["tts"]
        voice = tts["voice"]
        rate = tts["rate"]
        pitch = tts["pitch"]

        # Load templates
        template_path = TEMPLATES_DIR / f"{style_id}.json"
        if not template_path.exists():
            print(f"  SKIP {style_id}: no template file")
            continue

        with open(template_path, "r", encoding="utf-8") as f:
            templates = json.load(f)

        # Create output directory
        output_dir = ASSETS_DIR / style_id
        output_dir.mkdir(parents=True, exist_ok=True)

        for event in PREPACKAGED_EVENTS:
            phrases = templates.get(event, [])
            for i, phrase in enumerate(phrases):
                filename = f"{event}_{i + 1:02d}.mp3"
                output_path = output_dir / filename
                print(f"  Generating {style_id}/{filename}: {phrase[:30]}...")

                asyncio.run(generate_one(phrase, voice, rate, pitch, str(output_path)))

    print("Done! All audio files generated.")


if __name__ == "__main__":
    generate_all()
