from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from puppet_forge.defaults import DEFAULT_CHARACTERS
from puppet_forge.paths import outputs_dir
from puppet_forge.audio import write_wav
from puppet_forge.voice import SAMPLE_RATE, synthesize_text


PHRASES = [
    "hello local stage",
    "sound first, motion second",
    "the puppet voice is clear now",
]


def main() -> None:
    out_dir = outputs_dir() / "voice-auditions"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for character in DEFAULT_CHARACTERS:
        voice = character.voice.to_dict() if character.voice else {}
        safe_name = character.id.replace("/", "-")
        for index, phrase in enumerate(PHRASES, start=1):
            samples, visemes, word_cues = synthesize_text(phrase, voice, "bright" if index == 3 else "steady")
            wav_path = out_dir / f"{safe_name}-{index}.wav"
            write_wav(wav_path, samples, SAMPLE_RATE)
            manifest.append(
                {
                    "character": character.name,
                    "phrase": phrase,
                    "wav_path": str(wav_path),
                    "viseme_count": len(visemes),
                    "word_cues": word_cues,
                }
            )
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(out_dir), "manifest": str(manifest_path), "count": len(manifest)}, indent=2))


if __name__ == "__main__":
    main()
