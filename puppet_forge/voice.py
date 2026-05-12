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
PUNCTUATION_PAUSES = {
    ",": 0.115,
    ";": 0.135,
    ":": 0.13,
    ".": 0.185,
    "!": 0.215,
    "?": 0.225,
    "-": 0.075,
}


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
        elif char.isalnum() or char in ".,!?;:-'":
            units.append(char.lower())
    return units


def _char_duration(char: str, pace: float) -> float:
    pace = max(0.35, pace)
    if char == " ":
        return 0.055 / pace
    if char in PUNCTUATION_PAUSES:
        return PUNCTUATION_PAUSES[char] / pace
    if char in VOWELS:
        return 0.078 / pace
    if char.isdigit():
        return 0.062 / pace
    return 0.047 / pace


def _noise(index: int) -> float:
    value = (index * 1103515245 + 12345) & 0x7FFFFFFF
    return (value / 0x7FFFFFFF) * 2.0 - 1.0


def _emotion_settings(
    emotion: str,
    base: float,
    pace: float,
    brightness: float,
    grit: float,
) -> tuple[float, float, float, float, float, float]:
    emotion = (emotion or "steady").lower()
    energy = 1.0
    vibrato = 0.012
    if emotion == "bright":
        base *= 1.08
        brightness = min(1.0, brightness + 0.14)
        energy = 1.08
        vibrato = 0.018
    elif emotion == "careful":
        base *= 0.93
        pace *= 0.84
        energy = 0.82
        vibrato = 0.006
    elif emotion == "playful":
        base *= 1.12
        pace *= 1.12
        brightness = min(1.0, brightness + 0.1)
        energy = 1.12
        vibrato = 0.028
    elif emotion == "curious":
        base *= 1.04
        pace *= 0.98
        vibrato = 0.02
    elif emotion == "bold":
        base *= 0.98
        grit = min(1.0, grit + 0.08)
        energy = 1.18
    elif emotion == "gentle":
        base *= 0.96
        pace *= 0.92
        energy = 0.88
    return base, pace, brightness, grit, energy, vibrato


def _finish_word(word: list[str], start: float | None, end: float, cues: list[dict[str, Any]]) -> tuple[list[str], None]:
    if word and start is not None:
        cues.append({"word": "".join(word), "start": round(start, 3), "end": round(max(start, end), 3)})
    return [], None


def synthesize_text(
    text: str,
    voice: dict[str, Any],
    emotion: str = "steady",
) -> tuple[SampleBuffer, list[dict[str, Any]], list[dict[str, Any]]]:
    base = float(voice.get("base_frequency", 170.0))
    pace = float(voice.get("pace", 1.0))
    brightness = float(voice.get("brightness", 0.5))
    grit = float(voice.get("grit", 0.15))
    warmth = float(voice.get("warmth", 0.35))
    base, pace, brightness, grit, energy, vibrato = _emotion_settings(emotion, base, pace, brightness, grit)

    samples: SampleBuffer = []
    visemes: list[dict[str, Any]] = []
    word_cues: list[dict[str, Any]] = []
    current_word: list[str] = []
    word_start: float | None = None
    t = 0.0
    phase = 0.0
    units = phoneme_units(text)
    for idx, unit in enumerate(units):
        start = t
        if unit.isalnum() or unit == "'":
            if word_start is None:
                word_start = start
            current_word.append(unit)
        else:
            current_word, word_start = _finish_word(current_word, word_start, start, word_cues)

        dur = _char_duration(unit, pace)
        count = max(1, int(dur * SAMPLE_RATE))
        viseme = viseme_for(unit)
        if unit == " " or unit in PUNCTUATION_PAUSES:
            samples.extend([0.0] * count)
        else:
            freq = base * (1.0 + ((ord(unit[0]) % 7) - 3) * 0.027)
            if unit in VOWELS:
                freq *= {"a": 0.92, "e": 1.1, "i": 1.18, "o": 0.84, "u": 0.78, "y": 1.15}.get(unit, 1.0)
            amp = (0.25 if unit in VOWELS else 0.12) * energy
            for n in range(count):
                pos = n / count
                env = min(1.0, pos * 10.0, (1.0 - pos) * 8.0)
                now = t + n / SAMPLE_RATE
                wobble = 1.0 + math.sin(now * 8.0 + idx * 0.37) * vibrato
                phrase_lift = 1.0 + math.sin((idx + 1) * 0.71) * 0.018
                phase += 2.0 * math.pi * freq * wobble * phrase_lift / SAMPLE_RATE
                tone = math.sin(phase)
                harmonic = math.sin(phase * 2.0 + brightness) * brightness * 0.34
                breath = math.sin(phase * 0.5) * warmth * 0.045
                fricative = _noise(len(samples) + n + idx) * grit * (0.15 if unit not in VOWELS else 0.035)
                samples.append((tone + harmonic + breath + fricative) * amp * env)
        end = start + count / SAMPLE_RATE
        if viseme != "rest":
            visemes.append({"start": round(start, 3), "end": round(end, 3), "viseme": viseme, "token": unit})
        t = end
    _finish_word(current_word, word_start, t, word_cues)
    mastered = master_voice(samples, warmth_amount=warmth)
    return mastered, visemes, word_cues


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
    all_word_cues: list[dict[str, Any]] = []
    line_cues: list[dict[str, Any]] = []
    cursor = 0.0
    for index, line in enumerate(performance.get("lines", [])):
        character = by_id.get(line["character_id"]) or next(iter(by_id.values()))
        voice = character.get("voice") or {}
        samples, visemes, word_cues = synthesize_text(line["text"], voice, line.get("emotion", "steady"))
        line_start = cursor
        for event in visemes:
            shifted = dict(event)
            shifted["start"] = round(shifted["start"] + cursor, 3)
            shifted["end"] = round(shifted["end"] + cursor, 3)
            shifted["character_id"] = character["id"]
            shifted["character_name"] = character["name"]
            shifted["line_index"] = index
            all_visemes.append(shifted)
        for cue in word_cues:
            shifted_word = dict(cue)
            shifted_word["start"] = round(shifted_word["start"] + cursor, 3)
            shifted_word["end"] = round(shifted_word["end"] + cursor, 3)
            shifted_word["line_index"] = index
            shifted_word["character_id"] = character["id"]
            shifted_word["character_name"] = character["name"]
            all_word_cues.append(shifted_word)
        all_samples.extend(samples)
        pause = int(0.22 * SAMPLE_RATE)
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
                "word_count": sum(1 for cue in all_word_cues if cue["line_index"] == index),
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
        word_cues=all_word_cues,
    )
