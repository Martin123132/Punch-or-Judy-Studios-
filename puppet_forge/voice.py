from __future__ import annotations

import math
import re
import uuid
from pathlib import Path
from typing import Any

from .audio import SampleBuffer, duration_seconds, master_voice, write_wav
from .models import AudioTrack


SAMPLE_RATE = 22050
VOWELS = set("aeiouy")


def viseme_for(token: str) -> str:
    token = token.lower()
    if token in {"o", "u", "w"}:
        return "round"
    if token in {"a", "h"}:
        return "open"
    if token in {"e", "i", "y"}:
        return "wide"
    if token in {"f", "v", "s", "z", "t", "d", "n", "l"}:
        return "teeth"
    if token in {"m", "b", "p"}:
        return "closed"
    return "rest"


def phoneme_units(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text.strip())
    units: list[str] = []
    for char in cleaned:
        if char == " ":
            units.append(" ")
        elif char.isalnum() or char in ".,!?;:-":
            units.append(char.lower())
    return units


def _char_duration(char: str, pace: float) -> float:
    if char == " ":
        return 0.055 / max(0.35, pace)
    if char in ".,;:":
        return 0.095 / max(0.35, pace)
    if char in "!?":
        return 0.14 / max(0.35, pace)
    if char in VOWELS:
        return 0.075 / max(0.35, pace)
    return 0.045 / max(0.35, pace)


def _noise(index: int) -> float:
    value = (index * 1103515245 + 12345) & 0x7FFFFFFF
    return (value / 0x7FFFFFFF) * 2.0 - 1.0


def synthesize_text(text: str, voice: dict[str, Any], emotion: str = "steady") -> tuple[SampleBuffer, list[dict[str, Any]]]:
    base = float(voice.get("base_frequency", 170.0))
    pace = float(voice.get("pace", 1.0))
    brightness = float(voice.get("brightness", 0.5))
    grit = float(voice.get("grit", 0.15))
    warmth = float(voice.get("warmth", 0.35))
    if emotion == "bright":
        base *= 1.08
        brightness = min(1.0, brightness + 0.12)
    elif emotion == "careful":
        base *= 0.94
        pace *= 0.92
    elif emotion == "playful":
        base *= 1.12
        pace *= 1.08
    elif emotion == "curious":
        base *= 1.04

    samples: SampleBuffer = []
    visemes: list[dict[str, Any]] = []
    t = 0.0
    phase = 0.0
    units = phoneme_units(text)
    for idx, unit in enumerate(units):
        dur = _char_duration(unit, pace)
        start = t
        count = max(1, int(dur * SAMPLE_RATE))
        viseme = viseme_for(unit)
        if unit == " ":
            samples.extend([0.0] * count)
        else:
            freq = base * (1.0 + ((ord(unit[0]) % 7) - 3) * 0.027)
            if unit in VOWELS:
                freq *= {"a": 0.92, "e": 1.1, "i": 1.18, "o": 0.84, "u": 0.78, "y": 1.15}.get(unit, 1.0)
            amp = 0.26 if unit in VOWELS else 0.12
            for n in range(count):
                pos = n / count
                env = min(1.0, pos * 10.0, (1.0 - pos) * 8.0)
                wobble = 1.0 + math.sin((t + n / SAMPLE_RATE) * 8.0) * 0.012
                phase += 2.0 * math.pi * freq * wobble / SAMPLE_RATE
                tone = math.sin(phase)
                harmonic = math.sin(phase * 2.0 + brightness) * brightness * 0.34
                fricative = _noise(len(samples) + n + idx) * grit * (0.15 if unit not in VOWELS else 0.035)
                samples.append((tone + harmonic + fricative) * amp * env)
        end = start + count / SAMPLE_RATE
        if viseme != "rest" or unit in ".,!?":
            visemes.append({"start": round(start, 3), "end": round(end, 3), "viseme": viseme, "token": unit})
        t = end
    mastered = master_voice(samples, warmth_amount=warmth)
    return mastered, visemes


def synthesize_performance(
    performance: dict[str, Any],
    characters: list[dict[str, Any]],
    output_dir: str | Path,
) -> AudioTrack:
    by_id = {character["id"]: character for character in characters}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    all_samples: SampleBuffer = []
    all_visemes: list[dict[str, Any]] = []
    line_cues: list[dict[str, Any]] = []
    cursor = 0.0
    for index, line in enumerate(performance.get("lines", [])):
        character = by_id.get(line["character_id"]) or next(iter(by_id.values()))
        voice = character.get("voice") or {}
        samples, visemes = synthesize_text(line["text"], voice, line.get("emotion", "steady"))
        line_start = cursor
        for event in visemes:
            shifted = dict(event)
            shifted["start"] = round(shifted["start"] + cursor, 3)
            shifted["end"] = round(shifted["end"] + cursor, 3)
            shifted["character_id"] = character["id"]
            shifted["character_name"] = character["name"]
            all_visemes.append(shifted)
        all_samples.extend(samples)
        pause = int(0.16 * SAMPLE_RATE)
        all_samples.extend([0.0] * pause)
        line_end = cursor + len(samples) / SAMPLE_RATE
        line_cues.append(
            {
                "index": index,
                "start": round(line_start, 3),
                "end": round(line_end, 3),
                "character_id": character["id"],
                "character_name": character["name"],
                "emotion": line.get("emotion", "steady"),
                "text": line.get("text", ""),
            }
        )
        cursor = line_end + pause / SAMPLE_RATE
    track_id = f"aud-{uuid.uuid4().hex[:8]}"
    wav_path = output_dir / f"{track_id}.wav"
    write_wav(wav_path, all_samples, SAMPLE_RATE)
    return AudioTrack(
        id=track_id,
        performance_id=performance["id"],
        wav_path=str(wav_path),
        duration_seconds=round(duration_seconds(all_samples, SAMPLE_RATE), 3),
        visemes=all_visemes,
        line_cues=line_cues,
    )
