from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path

from puppet_forge import providers
from puppet_forge.defaults import DEFAULT_CHARACTERS, DEFAULT_SCENES
from puppet_forge.prompting import make_performance
from puppet_forge.renderer import render_performance
from puppet_forge.storage import connect, list_characters, list_scenes, save_performance, search_memory
from puppet_forge.voice import synthesize_performance


class StorageProviderRendererTests(unittest.TestCase):
    def test_storage_seeds_defaults_and_indexes_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with connect(Path(tmp) / "app.sqlite3") as con:
                self.assertGreaterEqual(len(list_characters(con)), 4)
                self.assertGreaterEqual(len(list_scenes(con)), 2)
                chars = list_characters(con)[:2]
                scene = list_scenes(con)[0]
                perf = make_performance(
                    prompt="memory spark",
                    script=f"{chars[0]['name']}: The lantern memory is local.",
                    characters=chars,
                    scene=scene,
                    provider="local",
                    model="local-scriptwright",
                )
                save_performance(con, perf)
                results = search_memory(con, "lantern")
                self.assertEqual(results[0]["performance_id"], perf.id)
                punctuated = search_memory(con, "lantern memory, local show?")
                self.assertTrue(punctuated)

    def test_local_provider_works_without_key(self) -> None:
        chars = [c.to_dict() for c in DEFAULT_CHARACTERS[:2]]
        scene = DEFAULT_SCENES[0].to_dict()
        result = providers.generate(
            provider="local",
            model="local-scriptwright",
            prompt="make it dance",
            characters=chars,
            scene=scene,
        )
        self.assertEqual(result["provider"], "local")
        self.assertIn(chars[0]["name"], result["script"] + chars[1]["name"])

    def test_renderer_creates_bundle_without_ffmpeg_requirement(self) -> None:
        chars = [c.to_dict() for c in DEFAULT_CHARACTERS[:2]]
        scene = DEFAULT_SCENES[0].to_dict()
        perf = make_performance(
            prompt="render test",
            script=f"{chars[0]['name']}: The frame appears.",
            characters=chars,
            scene=scene,
            provider="local",
            model="local-scriptwright",
        ).to_dict()
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["PUPPET_FORGE_HOME"] = tmp
            audio = synthesize_performance(perf, chars, Path(tmp) / "audio").to_dict()
            job = render_performance(perf, chars, scene, audio, fps=4)
            self.assertTrue(Path(job.preview_svg).exists())
            self.assertTrue(Path(job.html_path).exists())
            self.assertTrue(Path(job.manifest_path).exists())
            self.assertTrue(Path(job.package_path).exists())
            self.assertTrue(Path(job.wav_path).exists())
            self.assertTrue((Path(job.output_dir) / "stage.js").exists())
            self.assertTrue((Path(job.output_dir) / "subtitles.vtt").exists())
            self.assertTrue((Path(job.output_dir) / "script.txt").exists())
            manifest = json.loads(Path(job.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], 2)
            self.assertTrue(manifest["cast"][0]["rig"])
            self.assertTrue(manifest["audio"]["line_cues"])
            self.assertTrue(manifest["audio"]["word_cues"])
            self.assertEqual(manifest["motion_cues"]["gesture_source"], "word_cues")
            self.assertEqual(manifest["stage_style"]["renderer"], "local-2d-puppet-stage")


if __name__ == "__main__":
    unittest.main()
