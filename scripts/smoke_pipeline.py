from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from puppet_forge import providers
from puppet_forge.prompting import make_performance
from puppet_forge.renderer import render_performance
from puppet_forge.storage import connect, get_scene, list_characters, save_audio_track, save_performance
from puppet_forge.voice import synthesize_performance


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "smoke.sqlite3"
        with connect(db) as con:
            characters = list_characters(con)[:2]
            scene = get_scene(con, "workshop-stage")
            result = providers.generate(
                provider="local",
                model="local-scriptwright",
                prompt="Explain the local puppet forge pipeline in one tiny show.",
                characters=characters,
                scene=scene,
            )
            performance = make_performance(
                prompt="Explain the local puppet forge pipeline in one tiny show.",
                script=result["script"],
                characters=characters,
                scene=scene,
                provider=result["provider"],
                model=result["model"],
            )
            saved = save_performance(con, performance)
            audio = synthesize_performance(saved, list_characters(con), Path(tmp) / "audio").to_dict()
            save_audio_track(con, audio)
            render = render_performance(saved, list_characters(con), scene, audio).to_dict()
            print(json.dumps({"performance": saved["id"], "audio": audio["wav_path"], "render": render}, indent=2))


if __name__ == "__main__":
    main()
