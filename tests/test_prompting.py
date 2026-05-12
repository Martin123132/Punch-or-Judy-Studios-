from __future__ import annotations

import unittest

from puppet_forge.defaults import DEFAULT_CHARACTERS, DEFAULT_SCENES
from puppet_forge.prompting import build_system_prompt, local_scriptwright, make_performance, parse_script


class PromptingTests(unittest.TestCase):
    def test_prompt_compiler_preserves_character_traits_and_scene(self) -> None:
        chars = [c.to_dict() for c in DEFAULT_CHARACTERS[:2]]
        scene = DEFAULT_SCENES[0].to_dict()
        prompt = build_system_prompt(chars, scene, [{"character_name": "Nixie", "snippet": "local memory"}])
        self.assertIn("Nixie Lumen", prompt)
        self.assertIn("Workshop Stage", prompt)
        self.assertIn("Do not copy public fictional characters", prompt)
        self.assertIn("local memory", prompt)

    def test_local_scriptwright_returns_parseable_cast_lines(self) -> None:
        chars = [c.to_dict() for c in DEFAULT_CHARACTERS[:2]]
        scene = DEFAULT_SCENES[0].to_dict()
        script = local_scriptwright("turn a tune into motion", chars, scene)
        lines = parse_script(script, chars)
        self.assertGreaterEqual(len(lines), 5)
        self.assertTrue(all(line.character_id for line in lines))

    def test_make_performance_builds_domain_object(self) -> None:
        chars = [c.to_dict() for c in DEFAULT_CHARACTERS[:2]]
        scene = DEFAULT_SCENES[0].to_dict()
        perf = make_performance(
            prompt="tiny show",
            script="Nixie Lumen: We begin.\nMarlowe Veil: We observe.",
            characters=chars,
            scene=scene,
            provider="local",
            model="local-scriptwright",
        )
        self.assertEqual(perf.provider, "local")
        self.assertEqual(len(perf.lines), 2)


if __name__ == "__main__":
    unittest.main()

