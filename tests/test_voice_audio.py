from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

from puppet_forge.audio import master_voice, normalize, pgf_process
from puppet_forge.defaults import DEFAULT_CHARACTERS, DEFAULT_SCENES
from puppet_forge.prompting import make_performance
from puppet_forge.voice import SAMPLE_RATE, synthesize_performance, synthesize_text


class VoiceAudioTests(unittest.TestCase):
    def test_synthesize_text_creates_samples_and_visemes(self) -> None:
        samples, visemes = synthesize_text("Hello local stage!", DEFAULT_CHARACTERS[0].voice.to_dict())
        self.assertGreater(len(samples), SAMPLE_RATE // 2)
        self.assertTrue(any(event["viseme"] in {"open", "wide", "round"} for event in visemes))

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
            self.assertLess(track.line_cues[0]["start"], track.line_cues[0]["end"])
            with wave.open(track.wav_path, "rb") as wf:
                self.assertEqual(wf.getframerate(), SAMPLE_RATE)
                self.assertGreater(wf.getnframes(), 1000)


if __name__ == "__main__":
    unittest.main()
