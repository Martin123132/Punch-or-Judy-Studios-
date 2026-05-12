from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

from puppet_forge.audio import master_voice, normalize, pgf_process
from puppet_forge.defaults import DEFAULT_CHARACTERS, DEFAULT_SCENES
from puppet_forge.prompting import make_performance
from puppet_forge.voice import (
    SAMPLE_RATE,
    g2p_word,
    normalize_text,
    phoneme_units,
    synthesize_performance,
    synthesize_text,
    text_to_speech_units,
)


class VoiceAudioTests(unittest.TestCase):
    def test_normalize_text_and_g2p_handle_common_speech_rules(self) -> None:
        self.assertEqual(normalize_text("Hello—LOCAL & stage!"), "hello local and stage!")
        self.assertEqual(g2p_word("show"), ["sh", "aw"])
        self.assertEqual(g2p_word("thing")[:2], ["th", "ih"])
        self.assertIn("ng", g2p_word("thing"))
        self.assertEqual(g2p_word("voice")[-1], "s")
        units = text_to_speech_units("the puppet voice is clear now")
        symbols = [unit.symbol for unit in units if unit.symbol != "sil"]
        self.assertIn("dh", symbols)
        self.assertIn("p", symbols)
        self.assertIn("k", symbols)

    def test_synthesize_text_creates_samples_and_visemes(self) -> None:
        samples, visemes, word_cues = synthesize_text("Hello local stage!", DEFAULT_CHARACTERS[0].voice.to_dict())
        self.assertGreater(len(samples), SAMPLE_RATE // 2)
        self.assertTrue(any(event["viseme"] in {"open", "wide", "round"} for event in visemes))
        self.assertEqual([cue["word"] for cue in word_cues], ["hello", "local", "stage"])
        self.assertLessEqual(max(abs(sample) for sample in samples), 1.0)
        self.assertTrue(any(unit in {"ee", "oh", "ae"} for unit in phoneme_units("hello local stage")))

    def test_word_timing_punctuation_and_emotion_are_deterministic(self) -> None:
        voice = DEFAULT_CHARACTERS[0].voice.to_dict()
        plain, _, plain_words = synthesize_text("Hello local stage", voice, "steady")
        punctuated, _, punctuated_words = synthesize_text("Hello, local stage!", voice, "steady")
        careful, _, _ = synthesize_text("Hello local stage", voice, "careful")
        playful, _, _ = synthesize_text("Hello local stage", voice, "playful")
        self.assertGreater(len(punctuated), len(plain) + int(0.12 * SAMPLE_RATE))
        self.assertGreater(len(careful), len(playful))
        self.assertEqual(plain_words, synthesize_text("Hello local stage", voice, "steady")[2])
        self.assertEqual([cue["word"] for cue in punctuated_words], ["hello", "local", "stage"])
        seconds = len(plain) / SAMPLE_RATE
        self.assertGreater(seconds, 1.0)
        self.assertLess(seconds, 4.0)

    def test_pgf_mastering_keeps_samples_normalized(self) -> None:
        raw = [0.0, 1.8, -1.7, 0.2, -0.1, 0.0] * 20
        processed = master_voice(pgf_process(normalize(raw)))
        self.assertLessEqual(max(abs(x) for x in processed), 1.0)

    def test_performance_writes_wav(self) -> None:
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
            self.assertEqual(len(track.line_cues), 1)
            self.assertGreaterEqual(len(track.word_cues), 5)
            self.assertEqual(track.word_cues[0]["line_index"], 0)
            self.assertEqual(track.word_cues[0]["character_id"], chars[0]["id"])
            self.assertLess(track.line_cues[0]["start"], track.line_cues[0]["end"])
            with wave.open(track.wav_path, "rb") as wf:
                self.assertEqual(wf.getframerate(), SAMPLE_RATE)
                self.assertGreater(wf.getnframes(), 1000)


if __name__ == "__main__":
    unittest.main()
