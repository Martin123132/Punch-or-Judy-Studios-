from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .audio import SampleBuffer, clamp, duration_seconds, master_voice, normalize, write_wav
from .models import AudioTrack


SAMPLE_RATE = 22050
AUDIO_ENGINE_VERSION = "puppetvoice-0.9"
CLEAR_BASE_FREQUENCY = 158.0
WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?|[.,!?;:-]")
PUNCTUATION_PAUSES = {
    ",": 0.16,
    ";": 0.2,
    ":": 0.19,
    ".": 0.28,
    "!": 0.31,
    "?": 0.32,
    "-": 0.105,
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


@dataclass(frozen=True)
class UnitGesture:
    symbol: str
    duration: float
    energy: float = 1.0
    pitch: float = 0.0
    consonant: float = 1.0


@dataclass
class ResonatorState:
    y1: float = 0.0
    y2: float = 0.0


@dataclass
class SourceFilterState:
    phase: float = 0.0
    formant_states: list[ResonatorState] = field(default_factory=lambda: [ResonatorState(), ResonatorState(), ResonatorState()])
    previous_formants: tuple[float, float, float] = (500.0, 1500.0, 2500.0)
    dc_input: float = 0.0
    dc_output: float = 0.0
    noise_lowpass: float = 0.0
    radiation_previous: float = 0.0
    smoothing: float = 0.0


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
    "is": ["ih", "z"],
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


def _g(symbol: str, duration: float, energy: float = 1.0, pitch: float = 0.0, consonant: float = 1.0) -> UnitGesture:
    return UnitGesture(symbol, duration, energy=energy, pitch=pitch, consonant=consonant)


def _unit_word(*gestures: UnitGesture) -> tuple[UnitGesture, ...]:
    return gestures


UNIT_BANK: dict[str, tuple[UnitGesture, ...]] = {
    "the": _unit_word(
        _g("dh", 0.105, energy=1.1, pitch=0.015, consonant=1.35),
        _g("uh", 0.155, energy=0.98, pitch=0.006),
    ),
    "puppet": _unit_word(
        _g("p", 0.082, energy=1.24, pitch=0.012, consonant=1.8),
        _g("uh", 0.142, energy=1.02, pitch=0.012),
        _g("p", 0.072, energy=1.22, pitch=0.002, consonant=1.75),
        _g("eh", 0.142, energy=1.05, pitch=-0.006),
        _g("t", 0.07, energy=1.18, pitch=-0.012, consonant=1.65),
    ),
    "voice": _unit_word(
        _g("v", 0.13, energy=1.12, pitch=0.016, consonant=1.35),
        _g("oh", 0.17, energy=1.08, pitch=0.012),
        _g("ee", 0.13, energy=0.98, pitch=-0.002),
        _g("s", 0.125, energy=1.12, pitch=-0.014, consonant=1.45),
    ),
    "is": _unit_word(
        _g("ih", 0.13, energy=0.95, pitch=0.006),
        _g("z", 0.12, energy=1.03, pitch=-0.006, consonant=1.28),
    ),
    "clear": _unit_word(
        _g("k", 0.085, energy=1.28, pitch=0.008, consonant=1.85),
        _g("l", 0.105, energy=0.96, pitch=0.008),
        _g("ee", 0.19, energy=1.08, pitch=0.0),
        _g("r", 0.14, energy=0.95, pitch=-0.014),
    ),
    "now": _unit_word(
        _g("n", 0.12, energy=0.92, pitch=0.004),
        _g("aw", 0.25, energy=1.08, pitch=-0.018),
    ),
    "hello": _unit_word(
        _g("h", 0.105, energy=0.98, pitch=0.018, consonant=1.35),
        _g("eh", 0.18, energy=1.08, pitch=0.012),
        _g("l", 0.11, energy=0.96, pitch=-0.002),
        _g("oh", 0.19, energy=1.06, pitch=-0.012),
    ),
    "local": _unit_word(
        _g("l", 0.105, energy=0.98, pitch=0.012),
        _g("oh", 0.17, energy=1.07, pitch=0.006),
        _g("k", 0.085, energy=1.22, pitch=-0.002, consonant=1.75),
        _g("ah", 0.145, energy=1.0, pitch=-0.01),
        _g("l", 0.12, energy=0.94, pitch=-0.018),
    ),
    "stage": _unit_word(
        _g("s", 0.11, energy=1.14, pitch=0.014, consonant=1.55),
        _g("t", 0.075, energy=1.18, pitch=0.006, consonant=1.65),
        _g("ay", 0.18, energy=1.1, pitch=-0.004),
        _g("j", 0.11, energy=1.1, pitch=-0.016, consonant=1.45),
    ),
    "sound": _unit_word(
        _g("s", 0.12, energy=1.15, pitch=0.018, consonant=1.6),
        _g("aw", 0.205, energy=1.1, pitch=0.008),
        _g("n", 0.12, energy=0.94, pitch=-0.006),
        _g("d", 0.085, energy=1.1, pitch=-0.018, consonant=1.45),
    ),
    "first": _unit_word(
        _g("f", 0.13, energy=1.12, pitch=0.012, consonant=1.55),
        _g("er", 0.19, energy=1.03, pitch=0.0),
        _g("s", 0.095, energy=1.08, pitch=-0.01, consonant=1.45),
        _g("t", 0.075, energy=1.16, pitch=-0.018, consonant=1.6),
    ),
    "motion": _unit_word(
        _g("m", 0.12, energy=0.96, pitch=0.014),
        _g("oh", 0.17, energy=1.08, pitch=0.006),
        _g("sh", 0.135, energy=1.14, pitch=-0.006, consonant=1.55),
        _g("ah", 0.13, energy=0.96, pitch=-0.012),
        _g("n", 0.12, energy=0.92, pitch=-0.02),
    ),
    "second": _unit_word(
        _g("s", 0.11, energy=1.12, pitch=0.016, consonant=1.5),
        _g("eh", 0.145, energy=1.05, pitch=0.008),
        _g("k", 0.075, energy=1.18, pitch=0.0, consonant=1.7),
        _g("ah", 0.125, energy=0.95, pitch=-0.008),
        _g("n", 0.105, energy=0.92, pitch=-0.014),
        _g("d", 0.085, energy=1.08, pitch=-0.02, consonant=1.42),
    ),
}
UNIT_BANK_WORDS = frozenset(UNIT_BANK)

STRESSED_UNIT_WORDS: dict[str, float] = {
    "puppet": 1.15,
    "voice": 1.13,
    "clear": 1.16,
    "hello": 1.13,
    "stage": 1.14,
    "sound": 1.12,
    "motion": 1.13,
}
SOFT_FUNCTION_WORDS: dict[str, float] = {
    "the": 0.64,
    "is": 0.72,
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


def _word_stress(word: str) -> float:
    return SOFT_FUNCTION_WORDS.get(word, STRESSED_UNIT_WORDS.get(word, 1.0))


def _stress_duration_scale(stress: float) -> float:
    return clamp(1.0 + (stress - 1.0) * 0.16, 0.88, 1.05)


def _phrase_position(word_index: int, word_count: int) -> float:
    if word_count <= 1:
        return 0.0
    return clamp(word_index / max(1, word_count - 1), 0.0, 1.0)


def _phrase_pitch_at(position: float, pitch_swing: float) -> float:
    position = clamp(position, 0.0, 1.0)
    rise = math.sin(position * math.pi)
    settling_fall = position * 0.045
    return pitch_swing * 0.86 * rise - settling_fall


def _word_gap_duration(current_word: str, next_word: str, pace: float) -> float:
    if current_word in UNIT_BANK and next_word in UNIT_BANK:
        return 0.028 / pace
    return _pause_duration(" ", pace)


def _adjacent_unit_word(tokens: list[str], index: int, direction: int) -> bool:
    neighbor_index = index + direction
    if neighbor_index < 0 or neighbor_index >= len(tokens):
        return False
    current = tokens[index]
    neighbor = tokens[neighbor_index]
    return current in UNIT_BANK and neighbor in UNIT_BANK


def _blend_state_toward_next_unit(state: SourceFilterState, next_word: str | None) -> None:
    if not next_word or next_word not in UNIT_BANK:
        return
    first_spec = phoneme_spec(UNIT_BANK[next_word][0].symbol)
    state.previous_formants = tuple(
        current * 0.72 + upcoming * 0.28
        for current, upcoming in zip(state.previous_formants, first_spec.formants)
    )


def _phoneme_duration(spec: PhonemeSpec, pace: float, stress: float) -> float:
    duration = spec.duration * stress
    if spec.kind == "vowel":
        duration *= 1.18
    elif spec.kind in {"stop", "affricate"}:
        duration *= 0.9
    return duration / max(0.35, pace)


def _smoothstep(value: float) -> float:
    value = clamp(value, 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def _resonator_coefficients(frequency: float, bandwidth: float) -> tuple[float, float, float]:
    frequency = clamp(frequency, 80.0, SAMPLE_RATE * 0.46)
    bandwidth = clamp(bandwidth, 35.0, 1200.0)
    radius = math.exp(-math.pi * bandwidth / SAMPLE_RATE)
    theta = 2.0 * math.pi * frequency / SAMPLE_RATE
    gain = 1.0 - radius
    return gain, 2.0 * radius * math.cos(theta), -(radius * radius)


def _resonator_step(source: float, state: ResonatorState, frequency: float, bandwidth: float) -> float:
    gain, a1, a2 = _resonator_coefficients(frequency, bandwidth)
    value = gain * source + a1 * state.y1 + a2 * state.y2
    if not math.isfinite(value):
        state.y1 = 0.0
        state.y2 = 0.0
        return 0.0
    state.y2 = state.y1
    state.y1 = clamp(value, -8.0, 8.0)
    return state.y1


def _glottal_source(phase: float, open_quotient: float = 0.62) -> float:
    phase = phase % 1.0
    open_quotient = clamp(open_quotient, 0.45, 0.74)
    if phase < open_quotient:
        x = phase / open_quotient
        if x < 0.68:
            rise = 0.5 - 0.5 * math.cos(math.pi * x / 0.68)
            return rise * 1.22 - 0.42
        close = (x - 0.68) / 0.32
        return 0.76 - 1.46 * close
    close_x = (phase - open_quotient) / max(1e-6, 1.0 - open_quotient)
    return -0.34 * math.exp(-9.0 * close_x)


def _advance_glottis(state: SourceFilterState, frequency: float) -> float:
    state.phase = (state.phase + frequency / SAMPLE_RATE) % 1.0
    return state.phase


def _aspiration_noise(sample_index: int, state: SourceFilterState, brightness: float) -> float:
    raw = _noise(sample_index)
    raw2 = _noise(sample_index + 17)
    mixed = raw * 0.78 + raw2 * 0.22
    state.noise_lowpass = state.noise_lowpass * 0.68 + mixed * 0.32
    high = mixed - state.noise_lowpass * (0.58 - brightness * 0.22)
    return clamp(high, -1.0, 1.0)


def _bandwidths_for(spec: PhonemeSpec, brightness: float) -> tuple[float, float, float]:
    if spec.kind == "vowel":
        base = (82.0, 132.0, 220.0)
    elif spec.kind in {"liquid", "glide"}:
        base = (95.0, 155.0, 245.0)
    elif spec.kind == "nasal":
        base = (70.0, 120.0, 210.0)
    elif spec.kind in {"fricative", "affricate"}:
        base = (150.0, 260.0, 520.0)
    else:
        base = (115.0, 190.0, 340.0)
    scale = 1.06 - brightness * 0.18
    return (base[0] * scale, base[1] * scale, base[2] * scale)


def _interpolated_formants(state: SourceFilterState, target: tuple[float, float, float], pos: float, brightness: float) -> tuple[float, float, float]:
    amount = _smoothstep(min(1.0, pos * 1.65))
    scale = 0.97 + (brightness - 0.5) * 0.05
    formants = tuple((old + (new - old) * amount) * scale for old, new in zip(state.previous_formants, target))
    return (formants[0], formants[1], formants[2])


def _dc_block(value: float, state: SourceFilterState) -> float:
    out = value - state.dc_input + 0.995 * state.dc_output
    state.dc_input = value
    state.dc_output = clamp(out, -4.0, 4.0)
    return state.dc_output


def _vocal_tract_filter(
    excitation: float,
    spec: PhonemeSpec,
    state: SourceFilterState,
    pos: float,
    brightness: float,
    warmth: float,
    formants_override: tuple[float, float, float] | None = None,
    amplitudes_override: tuple[float, float, float] | None = None,
) -> float:
    formants = formants_override or _interpolated_formants(state, spec.formants, pos, brightness)
    amplitudes = amplitudes_override or spec.amplitudes
    bandwidths = _bandwidths_for(spec, brightness)
    total = 0.0
    for index, (frequency, bandwidth, amp) in enumerate(zip(formants, bandwidths, amplitudes)):
        if index >= len(state.formant_states):
            state.formant_states.append(ResonatorState())
        resonated = _resonator_step(excitation, state.formant_states[index], frequency, bandwidth)
        total += resonated * amp * (1.0 + index * (0.28 + brightness * 0.18))
    direct = 0.05 if spec.kind in {"vowel", "liquid", "glide", "nasal"} else 0.18
    filtered = _dc_block(total + excitation * direct, state)
    radiated = filtered - state.radiation_previous * 0.985
    state.radiation_previous = filtered
    filtered = radiated * 0.72 + filtered * 0.28
    smoothing = 0.18 + warmth * 0.18
    state.smoothing = state.smoothing * smoothing + filtered * (1.0 - smoothing)
    return clamp(state.smoothing, -3.0, 3.0)


def _envelope(pos: float, kind: str) -> float:
    if kind == "stop":
        return min(1.0, pos * 20.0, (1.0 - pos) * 7.0)
    if kind in {"fricative", "affricate"}:
        return min(1.0, pos * 7.0, (1.0 - pos) * 6.5)
    return min(1.0, pos * 9.0, (1.0 - pos) * 8.5)


def _unit_envelope(pos: float, kind: str, first: bool, last: bool) -> float:
    if kind == "stop":
        return _envelope(pos, kind)
    attack = min(1.0, pos * (9.0 if kind in {"fricative", "affricate"} else 13.0)) if first else 1.0
    release = min(1.0, (1.0 - pos) * (8.0 if kind in {"fricative", "affricate"} else 12.0)) if last else 1.0
    if kind in {"fricative", "affricate"}:
        body = 0.82 + 0.18 * math.sin(math.pi * pos)
    else:
        body = 0.94 + 0.06 * math.sin(math.pi * pos)
    return min(1.0, attack, release) * body


def _fade_for_kind(kind: str) -> int:
    if kind == "stop":
        return 44
    if kind in {"fricative", "affricate"}:
        return 112
    if kind == "vowel":
        return 148
    return 104


def _render_source_filter_sample(
    spec: PhonemeSpec,
    count: int,
    n: int,
    state: SourceFilterState,
    base_freq: float,
    pitch_target: float,
    brightness: float,
    warmth: float,
    grit: float,
    energy: float,
    sample_offset: int,
    consonant_boost: float = 1.0,
    unit_mode: bool = False,
    first: bool = True,
    last: bool = True,
    formants_override: tuple[float, float, float] | None = None,
    amplitudes_override: tuple[float, float, float] | None = None,
) -> float:
    burst_count = max(1, int(0.018 * SAMPLE_RATE))
    release_start = int(count * 0.42) if spec.kind == "stop" else 0
    nominal_freq = base_freq * (1.0 + pitch_target)
    pos = n / max(1, count - 1)
    sample_index = sample_offset + n
    wander = 0.006 + (0.006 if spec.kind in {"vowel", "liquid", "glide", "nasal"} else 0.0)
    freq = nominal_freq * (
        1.0
        + math.sin(sample_index / SAMPLE_RATE * 6.0) * wander
        + math.sin(sample_index / SAMPLE_RATE * 17.0) * 0.002
    )
    phase = _advance_glottis(state, freq)
    env = _unit_envelope(pos, spec.kind, first, last) if unit_mode else _envelope(pos, spec.kind)
    noise = _aspiration_noise(sample_index, state, brightness)
    glottal = _glottal_source(phase, 0.59 + warmth * 0.08)
    excitation = 0.0

    if spec.kind == "stop":
        if n < release_start:
            excitation = glottal * 0.055 if spec.voiced else 0.0
        else:
            release_pos = n - release_start
            if release_pos < burst_count:
                excitation += noise * spec.burst * (1.0 - release_pos / burst_count) * 1.25 * consonant_boost
            excitation += glottal * (0.46 if spec.voiced else 0.08)
    elif spec.kind == "affricate":
        if n < burst_count:
            excitation += noise * spec.burst * (1.0 - n / burst_count) * consonant_boost
        excitation += noise * max(spec.noise, 0.18) * 1.12 * consonant_boost
        if spec.voiced:
            excitation += glottal * 0.32
    elif spec.kind == "fricative":
        excitation += noise * max(spec.noise, 0.16) * (1.25 + brightness * 0.35) * consonant_boost
        if spec.voiced:
            excitation += glottal * 0.28
    elif spec.kind == "nasal":
        excitation = glottal * 0.58 + noise * grit * 0.015
    elif spec.kind in {"liquid", "glide"}:
        excitation = glottal * 0.72 + noise * (0.015 + grit * 0.018)
    else:
        excitation = glottal * 0.86 + noise * (0.035 + brightness * 0.012 + grit * 0.024)

    sample = _vocal_tract_filter(
        excitation,
        spec,
        state,
        pos,
        brightness,
        warmth,
        formants_override=formants_override,
        amplitudes_override=amplitudes_override,
    )
    if spec.kind in {"fricative", "affricate"}:
        sample += excitation * (0.22 + brightness * 0.1) * consonant_boost
    return clamp(sample * env * energy * 0.86)


def _render_phoneme(
    spec: PhonemeSpec,
    count: int,
    state: SourceFilterState,
    base_freq: float,
    pitch_target: float,
    brightness: float,
    warmth: float,
    grit: float,
    energy: float,
    sample_offset: int,
    consonant_boost: float = 1.0,
    unit_mode: bool = False,
    first: bool = True,
    last: bool = True,
) -> SampleBuffer:
    samples: SampleBuffer = []
    for n in range(count):
        samples.append(
            _render_source_filter_sample(
                spec,
                count,
                n,
                state,
                base_freq,
                pitch_target,
                brightness,
                warmth,
                grit,
                energy,
                sample_offset,
                consonant_boost=consonant_boost,
                unit_mode=unit_mode,
                first=first,
                last=last,
            )
        )
    state.previous_formants = spec.formants
    return samples


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


def _calibrated_voice_settings(voice: dict[str, Any]) -> tuple[float, float, float, float, float]:
    raw_base = float(voice.get("base_frequency", 170.0))
    raw_pace = float(voice.get("pace", 1.0))
    raw_brightness = float(voice.get("brightness", 0.5))
    raw_grit = float(voice.get("grit", 0.12))
    raw_warmth = float(voice.get("warmth", 0.45))
    base = CLEAR_BASE_FREQUENCY + clamp((raw_base - 170.0) * 0.12, -11.0, 11.0)
    pace = 1.0 + clamp((raw_pace - 1.0) * 0.24, -0.09, 0.09)
    brightness = 0.5 + clamp((raw_brightness - 0.5) * 0.16, -0.08, 0.08)
    grit = 0.045 + clamp(raw_grit, 0.0, 1.0) * 0.035
    warmth = 0.62 + clamp((raw_warmth - 0.5) * 0.14, -0.08, 0.08)
    return base, pace, brightness, grit, warmth


def _phrase_pitch(spoken_index: int, total_spoken: int, pitch_swing: float) -> float:
    phrase_pos = spoken_index / max(1, total_spoken - 1)
    return _phrase_pitch_at(phrase_pos, pitch_swing)


def _render_fallback_word(
    word: str,
    state: SourceFilterState,
    base: float,
    pace: float,
    brightness: float,
    warmth: float,
    grit: float,
    energy: float,
    pitch_swing: float,
    spoken_index: int,
    total_spoken: int,
    word_index: int,
    word_count: int,
    sample_offset: int,
) -> tuple[SampleBuffer, list[dict[str, Any]], list[dict[str, Any]], int]:
    samples: SampleBuffer = []
    visemes: list[dict[str, Any]] = []
    phoneme_cues: list[dict[str, Any]] = []
    phones = g2p_word(word)
    vowel_seen = False
    word_stress = _word_stress(word)
    position = _phrase_position(word_index, word_count)
    for phone in phones:
        spec = phoneme_spec(phone)
        stress = word_stress * (1.1 if spec.kind == "vowel" and not vowel_seen and len(word) > 3 else 1.0)
        if spec.kind == "vowel":
            vowel_seen = True
        count = max(1, int(_phoneme_duration(spec, pace, stress) * SAMPLE_RATE))
        pitch_target = _phrase_pitch(spoken_index, total_spoken, pitch_swing) + (word_stress - 1.0) * 0.034
        if stress > 1:
            pitch_target += 0.025
        before = len(samples)
        rendered = _render_phoneme(
            spec,
            count,
            state,
            base,
            pitch_target,
            brightness,
            warmth,
            grit,
            energy,
            sample_offset + len(samples),
        )
        _crossfade_append(samples, rendered, fade=_fade_for_kind(spec.kind))
        start = before / SAMPLE_RATE
        end = len(samples) / SAMPLE_RATE
        cue = {
            "phoneme": phone,
            "word": word,
            "start": round(start, 3),
            "end": round(end, 3),
            "viseme": spec.viseme,
            "kind": spec.kind,
            "render_source": "source-filter-fallback",
            "stress": round(word_stress, 3),
            "phrase_position": round(position, 3),
        }
        phoneme_cues.append(cue)
        if spec.viseme != "rest":
            visemes.append({"start": cue["start"], "end": cue["end"], "viseme": spec.viseme, "token": phone})
        spoken_index += 1
    return samples, visemes, phoneme_cues, spoken_index


def _lerp_tuple(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
    amount: float,
) -> tuple[float, float, float]:
    amount = clamp(amount, 0.0, 1.0)
    return (
        left[0] + (right[0] - left[0]) * amount,
        left[1] + (right[1] - left[1]) * amount,
        left[2] + (right[2] - left[2]) * amount,
    )


def _unit_transition_width(current: PhonemeSpec, neighbor: PhonemeSpec) -> float:
    if current.kind == "stop" or neighbor.kind == "stop":
        return 0.075
    if current.kind in {"fricative", "affricate"} or neighbor.kind in {"fricative", "affricate"}:
        return 0.11
    return 0.22


def _morphed_unit_tuple(
    current: tuple[float, float, float],
    previous: tuple[float, float, float] | None,
    next_value: tuple[float, float, float] | None,
    current_spec: PhonemeSpec,
    previous_spec: PhonemeSpec | None,
    next_spec: PhonemeSpec | None,
    pos: float,
) -> tuple[float, float, float]:
    result = current
    if previous and previous_spec:
        width = _unit_transition_width(current_spec, previous_spec)
        if pos < width:
            result = _lerp_tuple(previous, current, _smoothstep(pos / width))
    if next_value and next_spec:
        width = _unit_transition_width(current_spec, next_spec)
        if pos > 1.0 - width:
            result = _lerp_tuple(current, next_value, _smoothstep((pos - (1.0 - width)) / width))
    return result


def _morphed_unit_value(
    current: float,
    previous: float | None,
    next_value: float | None,
    current_spec: PhonemeSpec,
    previous_spec: PhonemeSpec | None,
    next_spec: PhonemeSpec | None,
    pos: float,
) -> float:
    result = current
    if previous is not None and previous_spec:
        width = _unit_transition_width(current_spec, previous_spec) * 1.35
        if pos < width:
            amount = _smoothstep(pos / width)
            result = previous + (current - previous) * amount
    if next_value is not None and next_spec:
        width = _unit_transition_width(current_spec, next_spec) * 1.35
        if pos > 1.0 - width:
            amount = _smoothstep((pos - (1.0 - width)) / width)
            result = current + (next_value - current) * amount
    return result


def _scaled_formants(formants: tuple[float, float, float], brightness: float) -> tuple[float, float, float]:
    scale = 0.97 + (brightness - 0.5) * 0.05
    return (formants[0] * scale, formants[1] * scale, formants[2] * scale)


def _render_unit_bank_word(
    word: str,
    state: SourceFilterState,
    base: float,
    pace: float,
    brightness: float,
    warmth: float,
    grit: float,
    energy: float,
    pitch_swing: float,
    spoken_index: int,
    total_spoken: int,
    word_index: int,
    word_count: int,
    connected_left: bool,
    connected_right: bool,
    sample_offset: int,
) -> tuple[SampleBuffer, list[dict[str, Any]], list[dict[str, Any]], int]:
    samples: SampleBuffer = []
    visemes: list[dict[str, Any]] = []
    phoneme_cues: list[dict[str, Any]] = []
    gestures = UNIT_BANK[word]
    stress = _word_stress(word)
    phrase_position = _phrase_position(word_index, word_count)
    word_pitch = _phrase_pitch_at(phrase_position, pitch_swing) + (stress - 1.0) * 0.036
    duration_scale = _stress_duration_scale(stress)
    segments: list[dict[str, Any]] = []
    cursor = 0
    for index, gesture in enumerate(gestures):
        spec = phoneme_spec(gesture.symbol)
        count = max(1, int((gesture.duration * duration_scale / max(0.35, pace)) * SAMPLE_RATE))
        segments.append(
            {
                "gesture": gesture,
                "spec": spec,
                "start": cursor,
                "end": cursor + count,
                "count": count,
                "pitch": word_pitch + gesture.pitch - index * 0.004,
                "energy": energy * gesture.energy * stress,
            }
        )
        cursor += count

    for index, segment in enumerate(segments):
        gesture = segment["gesture"]
        spec = segment["spec"]
        count = segment["count"]
        previous = segments[index - 1] if index > 0 else None
        next_segment = segments[index + 1] if index + 1 < len(segments) else None
        previous_spec = previous["spec"] if previous else None
        next_spec = next_segment["spec"] if next_segment else None
        for n in range(count):
            pos = n / max(1, count - 1)
            formants = _morphed_unit_tuple(
                spec.formants,
                previous_spec.formants if previous_spec else None,
                next_spec.formants if next_spec else None,
                spec,
                previous_spec,
                next_spec,
                pos,
            )
            amplitudes = _morphed_unit_tuple(
                spec.amplitudes,
                previous_spec.amplitudes if previous_spec else None,
                next_spec.amplitudes if next_spec else None,
                spec,
                previous_spec,
                next_spec,
                pos,
            )
            pitch_target = _morphed_unit_value(
                segment["pitch"],
                previous["pitch"] if previous else None,
                next_segment["pitch"] if next_segment else None,
                spec,
                previous_spec,
                next_spec,
                pos,
            )
            energy_target = _morphed_unit_value(
                segment["energy"],
                previous["energy"] if previous else None,
                next_segment["energy"] if next_segment else None,
                spec,
                previous_spec,
                next_spec,
                pos,
            )
            if previous_spec and previous_spec.kind in {"stop", "fricative", "affricate"} and spec.kind == "vowel" and pos < 0.16:
                energy_target *= 1.0 + (1.0 - pos / 0.16) * 0.1
                pitch_target += (1.0 - pos / 0.16) * 0.006
            samples.append(
                _render_source_filter_sample(
                    spec,
                    count,
                    n,
                    state,
                    base,
                    pitch_target,
                    brightness,
                    warmth,
                    grit,
                    energy_target,
                    sample_offset + segment["start"],
                    consonant_boost=gesture.consonant,
                    unit_mode=True,
                    first=index == 0 and not connected_left,
                    last=index == len(segments) - 1 and not connected_right,
                    formants_override=_scaled_formants(formants, brightness),
                    amplitudes_override=amplitudes,
                )
            )

        start = segment["start"] / SAMPLE_RATE
        end = segment["end"] / SAMPLE_RATE
        cue = {
            "phoneme": gesture.symbol,
            "word": word,
            "start": round(start, 3),
            "end": round(end, 3),
            "viseme": spec.viseme,
            "kind": spec.kind,
            "render_source": "unit-bank",
            "stress": round(stress, 3),
            "phrase_position": round(phrase_position, 3),
            "unit_mode": "continuous-unit",
        }
        phoneme_cues.append(cue)
        if spec.viseme != "rest":
            visemes.append({"start": cue["start"], "end": cue["end"], "viseme": spec.viseme, "token": gesture.symbol})
    state.previous_formants = phoneme_spec(gestures[-1].symbol).formants
    return samples, visemes, phoneme_cues, spoken_index + len(gestures)


def synthesize_text(
    text: str,
    voice: dict[str, Any],
    emotion: str = "steady",
) -> tuple[SampleBuffer, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    base, pace, brightness, grit, warmth = _calibrated_voice_settings(voice)
    base, pace, brightness, grit, energy, pitch_swing = _emotion_settings(emotion, base, pace, brightness, grit)
    tokens = tokenize_text(text)
    spoken_tokens = [token for token in tokens if token not in PUNCTUATION_PAUSES]
    total_spoken = max(1, sum(len(UNIT_BANK.get(token, tuple(g2p_word(token)))) for token in tokens if token not in PUNCTUATION_PAUSES))
    word_count = max(1, len(spoken_tokens))

    samples: SampleBuffer = []
    visemes: list[dict[str, Any]] = []
    word_cues: list[dict[str, Any]] = []
    phoneme_cues: list[dict[str, Any]] = []
    state = SourceFilterState()
    spoken_index = 0
    word_index = 0
    for index, token in enumerate(tokens):
        if token in PUNCTUATION_PAUSES:
            count = max(1, int(_pause_duration(token, pace) * SAMPLE_RATE))
            _crossfade_append(samples, [0.0] * count, fade=24)
            continue

        word_start_samples = len(samples)
        word_start = word_start_samples / SAMPLE_RATE
        stress = _word_stress(token)
        phrase_position = _phrase_position(word_index, word_count)
        if token in UNIT_BANK:
            rendered, word_visemes, word_phonemes, spoken_index = _render_unit_bank_word(
                token,
                state,
                base,
                pace,
                brightness,
                warmth,
                grit,
                energy,
                pitch_swing,
                spoken_index,
                total_spoken,
                word_index,
                word_count,
                _adjacent_unit_word(tokens, index, -1),
                _adjacent_unit_word(tokens, index, 1),
                len(samples),
            )
            render_source = "unit-bank"
        else:
            rendered, word_visemes, word_phonemes, spoken_index = _render_fallback_word(
                token,
                state,
                base,
                pace,
                brightness,
                warmth,
                grit,
                energy,
                pitch_swing,
                spoken_index,
                total_spoken,
                word_index,
                word_count,
                len(samples),
            )
            render_source = "source-filter-fallback"
        _crossfade_append(samples, rendered, fade=18)
        word_end = len(samples) / SAMPLE_RATE
        for cue in word_phonemes:
            shifted = dict(cue)
            shifted["start"] = round(shifted["start"] + word_start, 3)
            shifted["end"] = round(shifted["end"] + word_start, 3)
            phoneme_cues.append(shifted)
        for event in word_visemes:
            shifted_event = dict(event)
            shifted_event["start"] = round(shifted_event["start"] + word_start, 3)
            shifted_event["end"] = round(shifted_event["end"] + word_start, 3)
            visemes.append(shifted_event)
        word_cue = {
            "word": token,
            "start": round(word_start, 3),
            "end": round(max(word_start, word_end), 3),
            "render_source": render_source,
            "stress": round(stress, 3),
            "phrase_position": round(phrase_position, 3),
        }
        if render_source == "unit-bank":
            word_cue["unit_mode"] = "continuous-unit"
        word_cues.append(word_cue)
        if index < len(tokens) - 1:
            next_token = tokens[index + 1]
            if next_token not in PUNCTUATION_PAUSES:
                _blend_state_toward_next_unit(state, next_token)
                count = max(1, int(_word_gap_duration(token, next_token, pace) * SAMPLE_RATE))
                _crossfade_append(samples, [0.0] * count, fade=24)
        word_index += 1
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
