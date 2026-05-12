from __future__ import annotations

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
    audio_track_is_current,
    g2p_word,
    normalize_text,
    phoneme_units,
    synthesize_performance,
    synthesize_text,
    text_to_speech_units,
)


class VoiceAudioTests(unittest.TestCase):
    def test_normalize_text_and_g2p_handle_common_speech_rules(self) -> None:
        self.assertEqual(normalize_text("Hello\u2014LOCAL & stage!"), "hello - local and stage!")
        self.assertEqual(normalize_text("It\u2019s clear; don't stop"), "it is clear; do not stop")
        expected = {
            "the": ["dh", "uh"],
            "this": ["dh", "ih", "s"],
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
            self.assertLess(track.line_cues[0]["start"], track.line_cues[0]["end"])
            with wave.open(track.wav_path, "rb") as wf:
                self.assertEqual(wf.getframerate(), SAMPLE_RATE)
                self.assertGreater(wf.getnframes(), 1000)


if __name__ == "__main__":
    unittest.main()
