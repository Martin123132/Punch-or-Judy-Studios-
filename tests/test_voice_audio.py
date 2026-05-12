from __future__ import annotations

import math
import tempfile
import unittest
import wave
from pathlib import Path

from puppet_forge.audio import master_voice, normalize, pgf_process, rms
from puppet_forge.defaults import DEFAULT_CHARACTERS, DEFAULT_SCENES
from puppet_forge.prompting import make_performance
from puppet_forge.voice import (
    AUDIO_ENGINE_VERSION,
    SAMPLE_RATE,
    ResonatorState,
    UNIT_BANK_WORDS,
    audio_track_is_current,
    g2p_word,
    normalize_text,
    phoneme_units,
    synthesize_performance,
    synthesize_text,
    text_to_speech_units,
    _glottal_source,
    _resonator_coefficients,
    _resonator_step,
)


def _frequency_energy(samples: list[float], frequency: float) -> float:
    cosine = 0.0
    sine = 0.0
    for index, sample in enumerate(samples):
        angle = 2.0 * math.pi * frequency * index / SAMPLE_RATE
        cosine += sample * math.cos(angle)
        sine += sample * math.sin(angle)
    return math.sqrt(cosine * cosine + sine * sine) / max(1, len(samples))


DEMO_PHRASES = [
    "the puppet voice is clear now",
    "hello local stage",
    "sound first, motion second",
]


def _spoken_words(text: str) -> list[str]:
    return [word.strip(".,!?;:-") for word in text.split() if word.strip(".,!?;:-")]


DEMO_WORDS = {word for phrase in DEMO_PHRASES for word in _spoken_words(phrase)}


class VoiceAudioTests(unittest.TestCase):
    def test_normalize_text_and_g2p_handle_common_speech_rules(self) -> None:
        self.assertEqual(normalize_text("Hello\u2014LOCAL & stage!"), "hello - local and stage!")
        self.assertEqual(normalize_text("It\u2019s clear; don't stop"), "it is clear; do not stop")
        expected = {
            "the": ["dh", "uh"],
            "this": ["dh", "ih", "s"],
            "is": ["ih", "z"],
            "show": ["sh", "oh"],
            "voice": ["v", "oh", "ee", "s"],
            "clear": ["k", "l", "ee", "r"],
            "motion": ["m", "oh", "sh", "ah", "n"],
            "local": ["l", "oh", "k", "ah", "l"],
            "stage": ["s", "t", "ay", "j"],
            "puppet": ["p", "uh", "p", "eh", "t"],
            "through": ["th", "r", "oo"],
            "dance": ["d", "ae", "n", "s"],
        }
        for word, phones in expected.items():
            self.assertEqual(g2p_word(word), phones)
        self.assertEqual(g2p_word("make"), ["m", "ae", "k"])
        self.assertEqual(g2p_word("city")[0], "s")
        self.assertEqual(g2p_word("gentle")[0], "j")
        self.assertEqual(g2p_word("happy")[-1], "ee")
        self.assertEqual(g2p_word("letter").count("t"), 1)
        self.assertEqual(g2p_word("thing")[:2], ["th", "ih"])
        self.assertIn("ng", g2p_word("thing"))
        units = text_to_speech_units("the puppet voice is clear now")
        symbols = [unit.symbol for unit in units if unit.symbol != "sil"]
        self.assertIn("dh", symbols)
        self.assertIn("p", symbols)
        self.assertIn("k", symbols)

    def test_synthesize_text_creates_samples_and_timing_cues(self) -> None:
        samples, visemes, word_cues, phoneme_cues = synthesize_text(
            "Hello local stage!",
            DEFAULT_CHARACTERS[0].voice.to_dict(),
        )
        self.assertGreater(len(samples), SAMPLE_RATE // 2)
        self.assertTrue(any(event["viseme"] in {"open", "wide", "round"} for event in visemes))
        self.assertEqual([cue["word"] for cue in word_cues], ["hello", "local", "stage"])
        self.assertTrue(phoneme_cues)
        self.assertEqual(phoneme_cues[0]["phoneme"], "h")
        self.assertTrue(all(cue["start"] <= cue["end"] for cue in phoneme_cues))
        self.assertLessEqual(max(abs(sample) for sample in samples), 1.0)
        self.assertGreater(rms(samples), 0.02)
        self.assertTrue(any(unit in {"ee", "oh", "ae"} for unit in phoneme_units("hello local stage")))

    def test_v08_demo_phrases_use_unit_bank_with_aligned_cues(self) -> None:
        self.assertEqual(AUDIO_ENGINE_VERSION, "puppetvoice-0.8")
        self.assertTrue(DEMO_WORDS.issubset(UNIT_BANK_WORDS))
        for phrase in DEMO_PHRASES:
            samples, visemes, word_cues, phoneme_cues = synthesize_text(phrase, DEFAULT_CHARACTERS[0].voice.to_dict())
            self.assertEqual([cue["word"] for cue in word_cues], _spoken_words(phrase))
            self.assertTrue(all(cue["render_source"] == "unit-bank" for cue in word_cues))
            self.assertTrue(all(cue["render_source"] == "unit-bank" for cue in phoneme_cues))
            self.assertTrue(all("stress" in cue and "phrase_position" in cue for cue in word_cues))
            self.assertTrue(all("stress" in cue and "phrase_position" in cue for cue in phoneme_cues))
            self.assertTrue(visemes)
            for word in word_cues:
                phones = [cue for cue in phoneme_cues if cue["word"] == word["word"]]
                self.assertTrue(phones)
                self.assertGreaterEqual(phones[0]["start"], word["start"])
                self.assertLessEqual(phones[-1]["end"], word["end"] + 0.01)
            seconds = len(samples) / SAMPLE_RATE
            self.assertGreater(seconds, 1.2)
            self.assertLess(seconds, 3.2)
            self.assertGreater(rms(samples), 0.08)
            self.assertLessEqual(max(abs(sample) for sample in samples), 1.0)

    def test_v08_phrase_prosody_shortens_unit_gaps_and_marks_stress(self) -> None:
        voice = DEFAULT_CHARACTERS[0].voice.to_dict()
        samples, _, word_cues, _ = synthesize_text("the puppet voice is clear now", voice)
        by_word = {cue["word"]: cue for cue in word_cues}
        self.assertLess(by_word["the"]["stress"], 1.0)
        self.assertLess(by_word["is"]["stress"], 1.0)
        self.assertGreater(by_word["puppet"]["stress"], by_word["the"]["stress"])
        self.assertGreater(by_word["clear"]["stress"], by_word["is"]["stress"])
        the_segment = samples[int(by_word["the"]["start"] * SAMPLE_RATE) : int(by_word["the"]["end"] * SAMPLE_RATE)]
        clear_segment = samples[int(by_word["clear"]["start"] * SAMPLE_RATE) : int(by_word["clear"]["end"] * SAMPLE_RATE)]
        self.assertGreater(rms(clear_segment), rms(the_segment))

        _, _, punctuated_words, _ = synthesize_text("sound first, motion second", voice)
        gaps = {
            (left["word"], right["word"]): right["start"] - left["end"]
            for left, right in zip(punctuated_words, punctuated_words[1:])
        }
        self.assertLess(gaps[("sound", "first")], 0.06)
        self.assertGreater(gaps[("first", "motion")], gaps[("sound", "first")] + 0.07)
        self.assertLess(gaps[("motion", "second")], 0.06)

    def test_source_filter_primitives_are_stable_and_deterministic(self) -> None:
        coeffs = _resonator_coefficients(640.0, 120.0)
        self.assertTrue(all(math.isfinite(value) for value in coeffs))
        glottal = [_glottal_source(index / 64.0) for index in range(64)]
        self.assertGreater(max(glottal) - min(glottal), 0.8)
        self.assertTrue(all(math.isfinite(value) for value in glottal))

        first_state = ResonatorState()
        second_state = ResonatorState()
        first = [_resonator_step(_glottal_source((index * 0.011) % 1.0), first_state, 640.0, 120.0) for index in range(500)]
        second = [_resonator_step(_glottal_source((index * 0.011) % 1.0), second_state, 640.0, 120.0) for index in range(500)]
        self.assertEqual(first, second)
        self.assertTrue(all(math.isfinite(value) for value in first))
        self.assertLessEqual(max(abs(value) for value in first), 8.0)

    def test_voiced_vowels_have_broader_energy_than_a_single_beep(self) -> None:
        samples, _, _, _ = synthesize_text("aaaa eeee oooo", DEFAULT_CHARACTERS[0].voice.to_dict())
        window = samples[int(0.2 * SAMPLE_RATE) : int(0.2 * SAMPLE_RATE) + 4096]
        bands = [155, 310, 465, 620, 775, 930, 1240, 1550, 1860, 2400, 3000]
        energies = [_frequency_energy(window, band) for band in bands]
        top = max(energies)
        self.assertLess(top / sum(energies), 0.48)
        self.assertGreaterEqual(sum(1 for energy in energies if energy > top * 0.15), 3)

    def test_target_phrase_has_audible_consonant_energy(self) -> None:
        phrase = " ".join(DEMO_PHRASES)
        samples, _, _, phoneme_cues = synthesize_text(phrase, DEFAULT_CHARACTERS[0].voice.to_dict())
        thresholds = {"h": 0.06, "l": 0.1, "k": 0.025, "s": 0.08, "f": 0.08, "m": 0.08, "sh": 0.08, "d": 0.06}
        for phoneme, threshold in thresholds.items():
            matches = [cue for cue in phoneme_cues if cue["phoneme"] == phoneme]
            self.assertTrue(matches, phoneme)
            best = 0.0
            for cue in matches:
                segment = samples[int(cue["start"] * SAMPLE_RATE) : int(cue["end"] * SAMPLE_RATE)]
                best = max(best, rms(segment))
            self.assertGreater(best, threshold, phoneme)

    def test_word_timing_punctuation_and_emotion_are_deterministic(self) -> None:
        voice = DEFAULT_CHARACTERS[0].voice.to_dict()
        plain, _, plain_words, plain_phonemes = synthesize_text("Hello local stage", voice, "steady")
        punctuated, _, punctuated_words, punctuated_phonemes = synthesize_text("Hello, local stage!", voice, "steady")
        careful, _, _, _ = synthesize_text("Hello local stage", voice, "careful")
        playful, _, _, _ = synthesize_text("Hello local stage", voice, "playful")
        self.assertGreater(len(punctuated), len(plain) + int(0.12 * SAMPLE_RATE))
        self.assertGreater(len(careful), len(playful))
        again = synthesize_text("Hello local stage", voice, "steady")
        self.assertEqual(plain_words, again[2])
        self.assertEqual(plain_phonemes, again[3])
        self.assertEqual([cue["word"] for cue in punctuated_words], ["hello", "local", "stage"])
        self.assertEqual([cue["phoneme"] for cue in plain_phonemes], [cue["phoneme"] for cue in punctuated_phonemes])
        seconds = len(plain) / SAMPLE_RATE
        self.assertGreater(seconds, 1.0)
        self.assertLess(seconds, 4.0)

    def test_pgf_mastering_keeps_samples_normalized(self) -> None:
        raw = [0.0, 1.8, -1.7, 0.2, -0.1, 0.0] * 20
        processed = master_voice(pgf_process(normalize(raw)))
        self.assertLessEqual(max(abs(x) for x in processed), 1.0)

    def test_performance_writes_wav_and_marks_engine_version(self) -> None:
        chars = [c.to_dict() for c in DEFAULT_CHARACTERS[:2]]
        scene = DEFAULT_SCENES[0].to_dict()
        perf = make_performance(
            prompt="voice test",
            script="Nixie Lumen: The local voice wakes up.",
            characters=chars,
            scene=scene,
            provider="local",
            model="local-scriptwright",
        ).to_dict()
        with tempfile.TemporaryDirectory() as tmp:
            track = synthesize_performance(perf, chars, Path(tmp))
            self.assertTrue(Path(track.wav_path).exists())
            self.assertEqual(track.engine_version, AUDIO_ENGINE_VERSION)
            self.assertEqual(len(track.line_cues), 1)
            self.assertGreaterEqual(len(track.word_cues), 5)
            self.assertGreaterEqual(len(track.phoneme_cues), 10)
            self.assertEqual(track.word_cues[0]["line_index"], 0)
            self.assertEqual(track.word_cues[0]["character_id"], chars[0]["id"])
            self.assertEqual(track.phoneme_cues[0]["line_index"], 0)
            self.assertEqual(track.line_cues[0]["phoneme_count"], len(track.phoneme_cues))
            self.assertTrue(audio_track_is_current(track.to_dict()))
            self.assertFalse(audio_track_is_current({}))
            old_track = track.to_dict()
            old_track.pop("engine_version")
            self.assertFalse(audio_track_is_current(old_track))
            stale_track = track.to_dict()
            stale_track["engine_version"] = "puppetvoice-0.4"
            self.assertFalse(audio_track_is_current(stale_track))
            stale_track["engine_version"] = "puppetvoice-0.5"
            self.assertFalse(audio_track_is_current(stale_track))
            stale_track["engine_version"] = "puppetvoice-0.6"
            self.assertFalse(audio_track_is_current(stale_track))
            stale_track["engine_version"] = "puppetvoice-0.7"
            self.assertFalse(audio_track_is_current(stale_track))
            self.assertLess(track.line_cues[0]["start"], track.line_cues[0]["end"])
            with wave.open(track.wav_path, "rb") as wf:
                self.assertEqual(wf.getframerate(), SAMPLE_RATE)
                self.assertGreater(wf.getnframes(), 1000)


if __name__ == "__main__":
    unittest.main()
