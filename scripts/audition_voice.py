from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from puppet_forge.defaults import DEFAULT_CHARACTERS
from puppet_forge.paths import outputs_dir
from puppet_forge.audio import duration_seconds, rms, write_wav
from puppet_forge.voice import AUDIO_ENGINE_VERSION, SAMPLE_RATE, synthesize_text


PHRASE_SETS = {
    "v0.8-prosody-core": [
        "the puppet voice is clear now",
        "hello local stage",
        "sound first, motion second",
        "the voice is clear",
        "puppet voice now",
    ]
}


def _metrics(samples: list[float]) -> dict[str, float]:
    peak = max((abs(sample) for sample in samples), default=0.0)
    return {
        "duration_seconds": round(duration_seconds(samples, SAMPLE_RATE), 3),
        "peak": round(peak, 4),
        "rms": round(rms(samples), 4),
    }


def main() -> None:
    phrase_set = "v0.8-prosody-core"
    phrases = PHRASE_SETS[phrase_set]
    out_dir = outputs_dir() / "voice-auditions" / phrase_set
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for character in DEFAULT_CHARACTERS:
        voice = character.voice.to_dict() if character.voice else {}
        safe_name = character.id.replace("/", "-")
        for index, phrase in enumerate(phrases, start=1):
            emotion = "bright" if index == 3 else "steady"
            samples, visemes, word_cues, phoneme_cues = synthesize_text(phrase, voice, emotion)
            wav_path = out_dir / f"{safe_name}-{index:02d}.wav"
            write_wav(wav_path, samples, SAMPLE_RATE)
            manifest.append(
                {
                    "engine_version": AUDIO_ENGINE_VERSION,
                    "phrase_set": phrase_set,
                    "character": character.name,
                    "character_id": character.id,
                    "emotion": emotion,
                    "phrase": phrase,
                    "wav_path": str(wav_path),
                    **_metrics(samples),
                    "word_sources": [
                        {"word": cue["word"], "render_source": cue.get("render_source", "unknown")}
                        for cue in word_cues
                    ],
                    "phonemes": [cue["phoneme"] for cue in phoneme_cues],
                    "phoneme_cues": phoneme_cues,
                    "viseme_count": len(visemes),
                    "word_cues": word_cues,
                }
            )
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"output_dir": str(out_dir), "manifest": str(manifest_path), "count": len(manifest)}, indent=2))


if __name__ == "__main__":
    main()
