from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .audio import SampleBuffer, clamp, duration_seconds, master_voice, normalize, write_wav
from .models import AudioTrack


SAMPLE_RATE = 22050
AUDIO_ENGINE_VERSION = "puppetvoice-0.4"
MAX_HARMONIC = 14
WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?|[.,!?;:-]")
PUNCTUATION_PAUSES = {
    ",": 0.12,
    ";": 0.17,
    ":": 0.16,
    ".": 0.24,
    "!": 0.27,
    "?": 0.28,
    "-": 0.08,
}


@dataclass(frozen=True)
class PhonemeSpec:
    symbol: str
    kind: str
    viseme: str
    duration: float
    voiced: bool = False
    formants: tuple[float, float, float] = (500.0, 1500.0, 2500.0)
    amplitudes: tuple[float, float, float] = (1.0, 0.45, 0.2)
    noise: float = 0.0
    burst: float = 0.0


@dataclass(frozen=True)
class SpeechUnit:
    symbol: str
    word: str | None = None
    punctuation: str | None = None
    stress: float = 1.0


CONTRACTIONS = {
    "can't": "can not",
    "won't": "will not",
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "couldn't": "could not",
    "shouldn't": "should not",
    "wouldn't": "would not",
    "i'm": "i am",
    "i've": "i have",
    "i'll": "i will",
    "you're": "you are",
    "you've": "you have",
    "we're": "we are",
    "we've": "we have",
    "they're": "they are",
    "they've": "they have",
    "it's": "it is",
    "that's": "that is",
    "there's": "there is",
    "let's": "let us",
}


EXCEPTION_WORDS: dict[str, list[str]] = {
    "a": ["ah"],
    "ai": ["ay"],
    "and": ["ae", "n", "d"],
    "are": ["aa", "r"],
    "clear": ["k", "l", "ee", "r"],
    "dance": ["d", "ae", "n", "s"],
    "first": ["f", "er", "s", "t"],
    "hello": ["h", "eh", "l", "oh"],
    "local": ["l", "oh", "k", "ah", "l"],
    "motion": ["m", "oh", "sh", "ah", "n"],
    "now": ["n", "aw"],
    "of": ["ah", "v"],
    "one": ["w", "uh", "n"],
    "puppet": ["p", "uh", "p", "eh", "t"],
    "second": ["s", "eh", "k", "ah", "n", "d"],
    "show": ["sh", "oh"],
    "sound": ["s", "aw", "n", "d"],
    "speech": ["s", "p", "ee", "ch"],
    "stage": ["s", "t", "ay", "j"],
    "the": ["dh", "uh"],
    "them": ["dh", "eh", "m"],
    "then": ["dh", "eh", "n"],
    "there": ["dh", "eh", "r"],
    "these": ["dh", "ee", "z"],
    "they": ["dh", "ay"],
    "thing": ["th", "ih", "ng"],
    "this": ["dh", "ih", "s"],
    "those": ["dh", "oh", "z"],
    "though": ["dh", "oh"],
    "thought": ["th", "aw", "t"],
    "through": ["th", "r", "oo"],
    "to": ["t", "oo"],
    "voice": ["v", "oh", "ee", "s"],
    "was": ["w", "ah", "z"],
    "you": ["y", "oo"],
}


VOWEL_FORMANTS: dict[str, tuple[tuple[float, float, float], tuple[float, float, float], str]] = {
    "aa": ((760, 1180, 2600), (1.0, 0.48, 0.24), "open"),
    "ae": ((680, 1720, 2410), (1.0, 0.52, 0.24), "open"),
    "ah": ((640, 1250, 2550), (1.0, 0.46, 0.2), "open"),
    "aw": ((520, 900, 2400), (1.0, 0.5, 0.22), "round"),
    "ay": ((560, 1800, 2550), (1.0, 0.5, 0.2), "wide"),
    "eh": ((530, 1840, 2480), (1.0, 0.55, 0.24), "wide"),
    "ee": ((300, 2250, 3000), (1.0, 0.58, 0.28), "wide"),
    "ih": ((390, 1990, 2550), (1.0, 0.5, 0.22), "wide"),
    "oh": ((500, 900, 2600), (1.0, 0.48, 0.2), "round"),
    "oo": ((350, 760, 2400), (1.0, 0.44, 0.18), "round"),
    "uh": ((450, 1100, 2400), (1.0, 0.42, 0.18), "round"),
    "er": ((460, 1300, 1700), (1.0, 0.55, 0.28), "teeth"),
}


CONSONANTS: dict[str, PhonemeSpec] = {
    "b": PhonemeSpec("b", "stop", "closed", 0.065, voiced=True, formants=(220, 900, 2100), amplitudes=(0.5, 0.16, 0.08), burst=0.25),
    "ch": PhonemeSpec("ch", "affricate", "teeth", 0.105, noise=0.26, burst=0.34),
    "d": PhonemeSpec("d", "stop", "teeth", 0.06, voiced=True, formants=(260, 1600, 2600), amplitudes=(0.42, 0.18, 0.09), burst=0.24),
    "f": PhonemeSpec("f", "fricative", "teeth", 0.09, noise=0.17),
    "g": PhonemeSpec("g", "stop", "rest", 0.07, voiced=True, formants=(260, 1200, 2300), amplitudes=(0.45, 0.15, 0.08), burst=0.2),
    "h": PhonemeSpec("h", "fricative", "open", 0.065, noise=0.14),
    "j": PhonemeSpec("j", "affricate", "wide", 0.095, voiced=True, formants=(260, 1850, 2700), amplitudes=(0.45, 0.22, 0.11), noise=0.14, burst=0.22),
    "k": PhonemeSpec("k", "stop", "rest", 0.075, noise=0.06, burst=0.36),
    "l": PhonemeSpec("l", "liquid", "teeth", 0.075, voiced=True, formants=(360, 1200, 2600), amplitudes=(0.8, 0.3, 0.12)),
    "m": PhonemeSpec("m", "nasal", "closed", 0.08, voiced=True, formants=(250, 1050, 2200), amplitudes=(0.75, 0.18, 0.08)),
    "n": PhonemeSpec("n", "nasal", "teeth", 0.07, voiced=True, formants=(290, 1300, 2400), amplitudes=(0.68, 0.2, 0.08)),
    "ng": PhonemeSpec("ng", "nasal", "rest", 0.085, voiced=True, formants=(280, 1500, 2500), amplitudes=(0.65, 0.18, 0.08)),
    "p": PhonemeSpec("p", "stop", "closed", 0.07, burst=0.42),
    "r": PhonemeSpec("r", "liquid", "teeth", 0.08, voiced=True, formants=(360, 1150, 1750), amplitudes=(0.8, 0.34, 0.16)),
    "s": PhonemeSpec("s", "fricative", "teeth", 0.085, noise=0.22),
    "sh": PhonemeSpec("sh", "fricative", "round", 0.095, noise=0.24),
    "t": PhonemeSpec("t", "stop", "teeth", 0.065, burst=0.38),
    "th": PhonemeSpec("th", "fricative", "teeth", 0.09, noise=0.18),
    "dh": PhonemeSpec("dh", "fricative", "teeth", 0.075, voiced=True, formants=(260, 1500, 2500), amplitudes=(0.42, 0.18, 0.08), noise=0.07),
    "v": PhonemeSpec("v", "fricative", "teeth", 0.08, voiced=True, formants=(230, 1350, 2400), amplitudes=(0.44, 0.16, 0.08), noise=0.1),
    "w": PhonemeSpec("w", "glide", "round", 0.075, voiced=True, formants=(300, 760, 2400), amplitudes=(0.78, 0.3, 0.12)),
    "y": PhonemeSpec("y", "glide", "wide", 0.07, voiced=True, formants=(300, 2200, 3000), amplitudes=(0.76, 0.38, 0.16)),
    "z": PhonemeSpec("z", "fricative", "teeth", 0.08, voiced=True, formants=(250, 1500, 2600), amplitudes=(0.42, 0.18, 0.1), noise=0.14),
    "zh": PhonemeSpec("zh", "fricative", "round", 0.09, voiced=True, formants=(250, 1650, 2550), amplitudes=(0.42, 0.18, 0.1), noise=0.14),
}


def phoneme_spec(symbol: str) -> PhonemeSpec:
    if symbol in VOWEL_FORMANTS:
        formants, amplitudes, viseme = VOWEL_FORMANTS[symbol]
        return PhonemeSpec(symbol, "vowel", viseme, 0.115, voiced=True, formants=formants, amplitudes=amplitudes)
    return CONSONANTS.get(symbol, PhonemeSpec(symbol, "liquid", "rest", 0.055, voiced=True))


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.translate(
        {
            0x2018: "'",
            0x2019: "'",
            0x201A: "'",
            0x201B: "'",
            0x201C: '"',
            0x201D: '"',
            0x201E: '"',
            0x201F: '"',
            0x2013: "-",
            0x2014: "-",
            0x2212: "-",
        }
    )
    text = text.replace("&", " and ")
    for contraction, expansion in CONTRACTIONS.items():
        text = re.sub(rf"\b{re.escape(contraction)}\b", expansion, text)
    text = re.sub(r"\b([a-z]+)'s\b", r"\1 z", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\s*-\s*", " - ", text)
    text = re.sub(r"[^a-z0-9'.,!?;:\-\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize_text(text: str) -> list[str]:
    return WORD_RE.findall(normalize_text(text))


def _vowel_for_single(word: str, index: int) -> str:
    char = word[index]
    if char == "a":
        return "ah" if index + 1 == len(word) else "ae"
    if char == "e":
        return "eh" if index + 1 < len(word) else "ee"
    if char == "i":
        return "ih"
    if char == "o":
        return "oh"
    if char == "u":
        return "uh"
    if char == "y":
        return "ee" if index + 1 == len(word) else "ih"
    return "ah"


def g2p_word(word: str) -> list[str]:
    word = normalize_text(word).strip(".,!?;:- ")
    if not word:
        return []
    if word in EXCEPTION_WORDS:
        return EXCEPTION_WORDS[word][:]
    if word.endswith("ed") and len(word) > 3:
        root = g2p_word(word[:-2])
        return root + (["ih", "d"] if word[-3] in {"t", "d"} else ["d"])

    groups = [
        ("tion", ["sh", "ah", "n"]),
        ("sion", ["zh", "ah", "n"]),
        ("ture", ["ch", "er"]),
        ("dge", ["j"]),
        ("igh", ["ay"]),
        ("ough", ["oh"]),
        ("air", ["eh", "r"]),
        ("ear", ["ee", "r"]),
        ("er", ["er"]),
        ("ar", ["aa", "r"]),
        ("or", ["oh", "r"]),
        ("ee", ["ee"]),
        ("ea", ["ee"]),
        ("oo", ["oo"]),
        ("ou", ["aw"]),
        ("ow", ["aw"]),
        ("ai", ["ay"]),
        ("ay", ["ay"]),
        ("oa", ["oh"]),
        ("oy", ["oh", "ee"]),
        ("oi", ["oh", "ee"]),
        ("ch", ["ch"]),
        ("sh", ["sh"]),
        ("ng", ["ng"]),
        ("ph", ["f"]),
        ("wh", ["w"]),
        ("qu", ["k", "w"]),
        ("ck", ["k"]),
        ("th", ["dh"] if word in {"the", "this", "that", "these", "those", "then", "there", "they", "them"} else ["th"]),
    ]
    out: list[str] = []
    index = 0
    while index < len(word):
        char = word[index]
        next_char = word[index + 1] if index + 1 < len(word) else ""
        if index > 0 and char == word[index - 1] and char not in "aeiouy" and char != "s":
            index += 1
            continue
        if char == "e" and index == len(word) - 1 and len(word) > 2 and word[index - 1] not in "lr":
            index += 1
            continue
        match = None
        for text, phones in groups:
            if word.startswith(text, index):
                match = (text, phones)
                break
        if match:
            text, phones = match
            out.extend(phones)
            index += len(text)
            continue
        if char in "aeiouy":
            out.append(_vowel_for_single(word, index))
        elif char == "c":
            out.append("s" if next_char in "eiy" else "k")
        elif char == "g":
            out.append("j" if next_char in "eiy" else "g")
        elif char == "x":
            out.extend(["k", "s"])
        elif char in "bcdfhjklmnpqrstvwyz":
            out.append(char)
        index += 1
    return out


def text_to_speech_units(text: str) -> list[SpeechUnit]:
    units: list[SpeechUnit] = []
    for token in tokenize_text(text):
        if token in PUNCTUATION_PAUSES:
            units.append(SpeechUnit("sil", punctuation=token))
            continue
        phones = g2p_word(token)
        vowel_seen = False
        for phone in phones:
            spec = phoneme_spec(phone)
            stress = 1.12 if spec.kind == "vowel" and not vowel_seen and len(token) > 3 else 1.0
            if spec.kind == "vowel":
                vowel_seen = True
            units.append(SpeechUnit(phone, word=token, stress=stress))
        units.append(SpeechUnit("sil", punctuation=" "))
    if units and units[-1].symbol == "sil" and units[-1].punctuation == " ":
        units.pop()
    return units


def viseme_for(token: str) -> str:
    return phoneme_spec(token).viseme


def phoneme_units(text: str) -> list[str]:
    return [unit.symbol if unit.symbol != "sil" else " " for unit in text_to_speech_units(text)]


def audio_track_is_current(track: dict[str, Any]) -> bool:
    return (
        track.get("engine_version") == AUDIO_ENGINE_VERSION
        and bool(track.get("word_cues"))
        and bool(track.get("phoneme_cues"))
    )


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
    pitch_swing = 0.045
    if emotion == "bright":
        base *= 1.08
        brightness = min(1.0, brightness + 0.08)
        energy = 1.06
        pitch_swing = 0.06
    elif emotion == "careful":
        base *= 0.94
        pace *= 0.86
        energy = 0.9
        pitch_swing = 0.025
    elif emotion == "playful":
        base *= 1.12
        pace *= 1.1
        brightness = min(1.0, brightness + 0.08)
        energy = 1.08
        pitch_swing = 0.075
    elif emotion == "curious":
        base *= 1.03
        pace *= 0.96
        pitch_swing = 0.065
    elif emotion == "bold":
        base *= 0.98
        grit = min(1.0, grit + 0.04)
        energy = 1.12
    elif emotion == "gentle":
        base *= 0.96
        pace *= 0.9
        energy = 0.86
        pitch_swing = 0.03
    return base, pace, brightness, grit, energy, pitch_swing


def _pause_duration(punctuation: str | None, pace: float) -> float:
    if punctuation == " ":
        return 0.052 / pace
    return PUNCTUATION_PAUSES.get(punctuation or "", 0.07) / pace


def _phoneme_duration(spec: PhonemeSpec, pace: float, stress: float) -> float:
    duration = spec.duration * stress
    if spec.kind == "vowel":
        duration *= 1.18
    elif spec.kind in {"stop", "affricate"}:
        duration *= 0.9
    return duration / max(0.35, pace)


def _formant_weight(freq: float, formants: tuple[float, float, float], amplitudes: tuple[float, float, float], brightness: float) -> float:
    weight = 0.0
    bandwidths = (120.0, 190.0, 280.0)
    for formant, amp, bandwidth in zip(formants, amplitudes, bandwidths):
        weight += amp * math.exp(-((freq - formant) ** 2) / (2.0 * bandwidth * bandwidth))
    tilt = 1.0 / (1.0 + (freq / (1850.0 + brightness * 900.0)) ** 1.45)
    return weight * (0.34 + brightness * 0.36 + tilt)


def _voiced_weights(freq: float, spec: PhonemeSpec, brightness: float) -> tuple[list[tuple[int, float]], float]:
    weights: list[tuple[int, float]] = []
    norm = 0.0
    for harmonic in range(1, MAX_HARMONIC + 1):
        harmonic_freq = freq * harmonic
        if harmonic_freq > 4200:
            break
        weight = _formant_weight(harmonic_freq, spec.formants, spec.amplitudes, brightness) / harmonic
        weights.append((harmonic, weight))
        norm += abs(weight)
    return weights, max(0.12, norm)


def _voiced_sample(sample_index: int, phase: float, weights: list[tuple[int, float]], norm: float, warmth: float, grit: float) -> float:
    total = 0.0
    for harmonic, weight in weights:
        total += math.sin(phase * harmonic) * weight
    breath = _noise(sample_index) * grit * 0.012
    warm = math.sin(phase * 0.5) * warmth * 0.045
    return (total / norm) * 0.58 + warm + breath


def _filtered_noise(sample_index: int, spec: PhonemeSpec, brightness: float) -> float:
    raw = _noise(sample_index)
    raw2 = _noise(sample_index + 17)
    rough = raw * (0.72 + brightness * 0.18) + raw2 * 0.16
    if spec.symbol in {"s", "z"}:
        rough *= 1.08
    elif spec.symbol in {"sh", "zh", "ch"}:
        rough *= 0.98
    elif spec.symbol in {"f", "v", "th", "dh"}:
        rough *= 0.74
    return rough * spec.noise


def _envelope(pos: float, kind: str) -> float:
    if kind == "stop":
        return min(1.0, pos * 20.0, (1.0 - pos) * 7.0)
    if kind in {"fricative", "affricate"}:
        return min(1.0, pos * 7.0, (1.0 - pos) * 6.5)
    return min(1.0, pos * 9.0, (1.0 - pos) * 8.5)


def _fade_for_kind(kind: str) -> int:
    if kind == "stop":
        return 44
    if kind in {"fricative", "affricate"}:
        return 112
    if kind == "vowel":
        return 148
    return 104


def _render_phoneme(
    spec: PhonemeSpec,
    count: int,
    phase: float,
    base_freq: float,
    pitch_target: float,
    brightness: float,
    warmth: float,
    grit: float,
    energy: float,
    sample_offset: int,
) -> tuple[SampleBuffer, float]:
    samples: SampleBuffer = []
    burst_count = max(1, int(0.018 * SAMPLE_RATE))
    nominal_freq = base_freq * (1.0 + pitch_target)
    weights, norm = _voiced_weights(nominal_freq, spec, brightness) if spec.voiced else ([], 1.0)
    for n in range(count):
        pos = n / max(1, count - 1)
        freq = nominal_freq * (1.0 + math.sin((sample_offset + n) / SAMPLE_RATE * 6.0) * 0.006)
        phase += 2.0 * math.pi * freq / SAMPLE_RATE
        env = _envelope(pos, spec.kind)
        sample = 0.0
        if spec.voiced:
            sample = _voiced_sample(sample_offset + n, phase, weights, norm, warmth, grit)
        if spec.noise:
            sample += _filtered_noise(sample_offset + n, spec, brightness) * (0.62 if spec.voiced else 1.0)
        if spec.burst and n < burst_count:
            sample += _noise(sample_offset + n + 101) * spec.burst * (1.0 - n / burst_count)
        samples.append(clamp(sample * env * energy * 0.62))
    return samples, phase


def _crossfade_append(target: SampleBuffer, incoming: SampleBuffer, fade: int = 96) -> None:
    if not target or not incoming:
        target.extend(incoming)
        return
    size = min(fade, len(target), len(incoming))
    for i in range(size):
        ratio = (i + 1) / (size + 1)
        target[-size + i] = target[-size + i] * (1.0 - ratio) + incoming[i] * ratio
    target.extend(incoming[size:])


def _finish_word(word: str | None, start: float | None, end: float, cues: list[dict[str, Any]]) -> tuple[None, None]:
    if word and start is not None:
        cues.append({"word": word, "start": round(start, 3), "end": round(max(start, end), 3)})
    return None, None


def synthesize_text(
    text: str,
    voice: dict[str, Any],
    emotion: str = "steady",
) -> tuple[SampleBuffer, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    base = float(voice.get("base_frequency", 170.0))
    pace = float(voice.get("pace", 1.0))
    brightness = 0.2 + clamp(float(voice.get("brightness", 0.5)), 0.0, 1.0) * 0.62
    grit = clamp(float(voice.get("grit", 0.12)), 0.0, 1.0) * 0.22
    warmth = clamp(float(voice.get("warmth", 0.35)), 0.0, 1.0)
    base, pace, brightness, grit, energy, pitch_swing = _emotion_settings(emotion, base, pace, brightness, grit)
    units = text_to_speech_units(text)
    spoken_units = [unit for unit in units if unit.symbol != "sil"]
    total_spoken = max(1, len(spoken_units))

    samples: SampleBuffer = []
    visemes: list[dict[str, Any]] = []
    word_cues: list[dict[str, Any]] = []
    phoneme_cues: list[dict[str, Any]] = []
    current_word: str | None = None
    word_start: float | None = None
    t = 0.0
    phase = 0.0
    spoken_index = 0
    for unit in units:
        start = t
        if unit.symbol == "sil":
            current_word, word_start = _finish_word(current_word, word_start, start, word_cues)
            count = max(1, int(_pause_duration(unit.punctuation, pace) * SAMPLE_RATE))
            _crossfade_append(samples, [0.0] * count, fade=24)
            t += count / SAMPLE_RATE
            continue

        if current_word != unit.word:
            current_word, word_start = _finish_word(current_word, word_start, start, word_cues)
            current_word = unit.word
            word_start = start

        spec = phoneme_spec(unit.symbol)
        dur = _phoneme_duration(spec, pace, unit.stress)
        count = max(1, int(dur * SAMPLE_RATE))
        phrase_pos = spoken_index / total_spoken
        pitch_target = pitch_swing * math.sin(phrase_pos * math.pi * 1.35) - phrase_pos * 0.055
        if unit.stress > 1:
            pitch_target += 0.025
        rendered, phase = _render_phoneme(
            spec,
            count,
            phase,
            base,
            pitch_target,
            brightness,
            warmth,
            grit,
            energy,
            len(samples),
        )
        _crossfade_append(samples, rendered, fade=_fade_for_kind(spec.kind))
        end = start + count / SAMPLE_RATE
        cue = {
            "phoneme": unit.symbol,
            "word": unit.word,
            "start": round(start, 3),
            "end": round(end, 3),
            "viseme": spec.viseme,
            "kind": spec.kind,
        }
        phoneme_cues.append(cue)
        if spec.viseme != "rest":
            visemes.append({"start": cue["start"], "end": cue["end"], "viseme": spec.viseme, "token": unit.symbol})
        t = end
        spoken_index += 1
    _finish_word(current_word, word_start, t, word_cues)
    mastered = master_voice(samples, warmth_amount=warmth * 0.36, cleanup=False)
    return normalize(mastered, target=0.86), visemes, word_cues, phoneme_cues


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
    all_phoneme_cues: list[dict[str, Any]] = []
    line_cues: list[dict[str, Any]] = []
    cursor = 0.0
    for index, line in enumerate(performance.get("lines", [])):
        character = by_id.get(line["character_id"]) or next(iter(by_id.values()))
        voice = character.get("voice") or {}
        samples, visemes, word_cues, phoneme_cues = synthesize_text(line["text"], voice, line.get("emotion", "steady"))
        line_start = cursor
        for event in visemes:
            shifted = dict(event)
            shifted["start"] = round(shifted["start"] + cursor, 3)
            shifted["end"] = round(shifted["end"] + cursor, 3)
            shifted["character_id"] = character["id"]
            shifted["character_name"] = character["name"]
            shifted["line_index"] = index
            all_visemes.append(shifted)
        line_word_count = 0
        for cue in word_cues:
            shifted_word = dict(cue)
            shifted_word["start"] = round(shifted_word["start"] + cursor, 3)
            shifted_word["end"] = round(shifted_word["end"] + cursor, 3)
            shifted_word["line_index"] = index
            shifted_word["character_id"] = character["id"]
            shifted_word["character_name"] = character["name"]
            all_word_cues.append(shifted_word)
            line_word_count += 1
        line_phoneme_count = 0
        for cue in phoneme_cues:
            shifted_phone = dict(cue)
            shifted_phone["start"] = round(shifted_phone["start"] + cursor, 3)
            shifted_phone["end"] = round(shifted_phone["end"] + cursor, 3)
            shifted_phone["line_index"] = index
            shifted_phone["character_id"] = character["id"]
            shifted_phone["character_name"] = character["name"]
            all_phoneme_cues.append(shifted_phone)
            line_phoneme_count += 1
        all_samples.extend(samples)
        pause = int(0.2 * SAMPLE_RATE)
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
                "word_count": line_word_count,
                "phoneme_count": line_phoneme_count,
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
        phoneme_cues=all_phoneme_cues,
        engine_version=AUDIO_ENGINE_VERSION,
    )
