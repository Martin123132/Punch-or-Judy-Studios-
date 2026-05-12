from __future__ import annotations

import json
import mimetypes
import os
import shutil
import sys
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import __version__
from . import providers
from .paths import app_data_dir, outputs_dir, repo_root
from .prompting import make_performance, slugify
from .renderer import render_performance
from .storage import (
    connect,
    get_character,
    get_performance,
    get_scene,
    list_audio_tracks,
    list_characters,
    list_performances,
    list_projects,
    list_render_jobs,
    list_scenes,
    list_settings,
    save_audio_track,
    save_character,
    save_performance,
    save_render_job,
    save_scene,
    search_memory,
    set_setting,
)
from .voice import audio_track_is_current, synthesize_performance


ROOT = repo_root()
STATIC_DIR = ROOT / "puppet_forge" / "static"
TEMPLATE_DIR = ROOT / "puppet_forge" / "templates"


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, indent=2).encode("utf-8")


def _load_runtime_settings() -> None:
    with connect() as con:
        settings = list_settings(con)
    for key, value in settings.items():
        if key.startswith("env.") and value:
            os.environ[key[4:]] = str(value)


def doctor() -> dict[str, object]:
    env = os.environ
    return {
        "version": __version__,
        "python": sys.version.split()[0],
        "data_dir": str(app_data_dir()),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "providers": {
            "openai": bool(env.get("OPENAI_API_KEY")),
            "anthropic": bool(env.get("ANTHROPIC_API_KEY")),
            "gemini": bool(env.get("GEMINI_API_KEY")),
            "ollama_host": env.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
            "ollama_model": env.get("OLLAMA_MODEL", "llama3"),
        },
    }


class PuppetForgeHandler(BaseHTTPRequestHandler):
    server_version = "PuppetForge/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stdout.write("[puppet-forge] " + fmt % args + "\n")

    def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: object, status: int = 200) -> None:
        self._send(status, _json_bytes(payload), "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("content-length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw or "{}")

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._json({"ok": False, "error": "File not found"}, HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self._send(HTTPStatus.OK, path.read_bytes(), content_type)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path == "/":
                self._send_file(TEMPLATE_DIR / "index.html")
            elif path == "/healthz":
                self._json({"ok": True, "version": __version__})
            elif path == "/api/state":
                self._api_state()
            elif path == "/api/doctor":
                self._json({"ok": True, "doctor": doctor()})
            elif path == "/api/memory":
                query = parse_qs(parsed.query).get("q", [""])[0]
                with connect() as con:
                    self._json({"ok": True, "results": search_memory(con, query)})
            elif path.startswith("/static/"):
                candidate = (STATIC_DIR / path.removeprefix("/static/")).resolve()
                if STATIC_DIR.resolve() not in candidate.parents and candidate != STATIC_DIR.resolve():
                    self._json({"ok": False, "error": "Bad static path"}, HTTPStatus.BAD_REQUEST)
                else:
                    self._send_file(candidate)
            elif path.startswith("/outputs/"):
                candidate = (outputs_dir() / path.removeprefix("/outputs/")).resolve()
                if outputs_dir().resolve() not in candidate.parents and candidate != outputs_dir().resolve():
                    self._json({"ok": False, "error": "Bad output path"}, HTTPStatus.BAD_REQUEST)
                else:
                    self._send_file(candidate)
            else:
                self._json({"ok": False, "error": "Not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:  # pragma: no cover - last-ditch server guard
            self._json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            payload = self._read_json()
            if path == "/api/settings":
                self._api_save_settings(payload)
            elif path == "/api/characters":
                self._api_save_character(payload)
            elif path == "/api/scenes":
                self._api_save_scene(payload)
            elif path == "/api/performances/generate":
                self._api_generate_performance(payload)
            elif path == "/api/audio":
                self._api_generate_audio(payload)
            elif path == "/api/render":
                self._api_render(payload)
            else:
                self._json({"ok": False, "error": "Not found"}, HTTPStatus.NOT_FOUND)
        except providers.ProviderError as exc:
            self._json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover - last-ditch server guard
            self._json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _api_state(self) -> None:
        with connect() as con:
            self._json(
                {
                    "ok": True,
                    "projects": list_projects(con),
                    "characters": list_characters(con),
                    "scenes": list_scenes(con),
                    "performances": list_performances(con),
                    "renders": [_public_paths(render) for render in list_render_jobs(con)],
                    "settings": list_settings(con),
                    "providers": providers.available_providers(),
                    "doctor": doctor(),
                }
            )

    def _api_save_settings(self, payload: dict) -> None:
        allowed_env = {
            "OPENAI_API_KEY",
            "OPENAI_MODEL_DEFAULT",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_MODEL_DEFAULT",
            "GEMINI_API_KEY",
            "GEMINI_MODEL_DEFAULT",
            "OLLAMA_HOST",
            "OLLAMA_MODEL",
            "PUPPET_FORGE_OFFLINE",
        }
        with connect() as con:
            for key, value in payload.items():
                if key in allowed_env:
                    os.environ[key] = str(value)
                    set_setting(con, f"env.{key}", value)
                else:
                    set_setting(con, key, value)
        self._json({"ok": True, "doctor": doctor()})

    def _api_save_character(self, payload: dict) -> None:
        name = (payload.get("name") or "New Character").strip()
        payload["id"] = payload.get("id") or f"char-{slugify(name)}-{uuid.uuid4().hex[:4]}"
        payload["name"] = name
        payload.setdefault("role", "original puppet performer")
        payload.setdefault("lore", "A new original character waiting for a first scene.")
        payload.setdefault("speech_style", "clear, vivid, performable")
        payload.setdefault("traits", [])
        payload.setdefault("emotional_range", 0.7)
        payload.setdefault("chaos", 0.25)
        payload.setdefault("kindness", 0.65)
        payload.setdefault(
            "voice",
            {
                "id": f"voice-{payload['id']}",
                "name": f"{name} Voice",
                "base_frequency": 175,
                "pace": 1.0,
                "brightness": 0.5,
                "grit": 0.12,
                "warmth": 0.42,
                "formality": 0.5,
            },
        )
        payload.setdefault(
            "rig",
            {
                "id": f"rig-{payload['id']}",
                "name": f"{name} Rig",
                "body_color": "#b85f37",
                "accent_color": "#ffd166",
                "eye_color": "#f7fbff",
                "mouth_color": "#171219",
                "silhouette": "rounded",
                "scale": 1.0,
            },
        )
        with connect() as con:
            saved = save_character(con, payload)
        self._json({"ok": True, "character": saved})

    def _api_save_scene(self, payload: dict) -> None:
        name = (payload.get("name") or "New Scene").strip()
        payload["id"] = payload.get("id") or f"scene-{slugify(name)}-{uuid.uuid4().hex[:4]}"
        payload["name"] = name
        payload.setdefault("setting", "A small original stage.")
        payload.setdefault("mood", "curious")
        payload.setdefault("lighting", "warm theatre wash")
        payload.setdefault("camera", "center-stage two-shot")
        payload.setdefault("notes", "")
        with connect() as con:
            saved = save_scene(con, payload)
        self._json({"ok": True, "scene": saved})

    def _selected_characters(self, con, ids: list[str] | None) -> list[dict]:
        if ids:
            selected = [get_character(con, item) for item in ids]
            selected = [item for item in selected if item]
        else:
            selected = list_characters(con)[:2]
        if not selected:
            raise ValueError("No characters available.")
        return selected

    def _api_generate_performance(self, payload: dict) -> None:
        prompt = (payload.get("prompt") or "").strip()
        if not prompt:
            raise ValueError("Prompt is required.")
        provider = (payload.get("provider") or "local").strip()
        model = payload.get("model") or providers.default_model(provider)
        with connect() as con:
            characters = self._selected_characters(con, payload.get("character_ids") or [])
            scene = get_scene(con, payload.get("scene_id") or "workshop-stage") or list_scenes(con)[0]
            memory = search_memory(con, prompt, limit=6)
            try:
                result = providers.generate(
                    provider=provider,
                    model=model,
                    prompt=prompt,
                    characters=characters,
                    scene=scene,
                    memory=memory,
                    temperature=float(payload.get("temperature", 0.7)),
                )
            except providers.ProviderError:
                if not payload.get("fallback_local", True):
                    raise
                result = providers.generate(
                    provider="local",
                    model="local-scriptwright",
                    prompt=prompt,
                    characters=characters,
                    scene=scene,
                    memory=memory,
                )
            performance = make_performance(
                prompt=prompt,
                script=result["script"],
                characters=characters,
                scene=scene,
                provider=result["provider"],
                model=result["model"],
            )
            saved = save_performance(con, performance)
        self._json({"ok": True, "performance": saved, "script": result["script"]})

    def _api_generate_audio(self, payload: dict) -> None:
        performance_id = payload.get("performance_id")
        with connect() as con:
            performance = get_performance(con, performance_id)
            if not performance:
                raise ValueError("Performance not found.")
            characters = list_characters(con)
            track = synthesize_performance(performance, characters, outputs_dir() / performance_id)
            saved = save_audio_track(con, track.to_dict())
        self._json({"ok": True, "audio": _public_paths(saved)})

    def _api_render(self, payload: dict) -> None:
        performance_id = payload.get("performance_id")
        with connect() as con:
            performance = get_performance(con, performance_id)
            if not performance:
                raise ValueError("Performance not found.")
            scene = get_scene(con, performance["scene_id"]) or list_scenes(con)[0]
            characters = list_characters(con)
            tracks = list_audio_tracks(con, performance_id)
            if tracks and audio_track_is_current(tracks[0]):
                audio = tracks[0]
            else:
                audio_track = synthesize_performance(performance, characters, outputs_dir() / performance_id)
                audio = save_audio_track(con, audio_track.to_dict())
            job = render_performance(performance, characters, scene, audio, fps=int(payload.get("fps", 8)))
            saved = save_render_job(con, job.to_dict())
        self._json({"ok": True, "render": _public_paths(saved)})


def _public_paths(payload: dict) -> dict:
    out = dict(payload)
    root = outputs_dir().resolve()
    for key in ("wav_path", "mp4_path", "html_path", "preview_svg", "output_dir", "package_path", "manifest_path"):
        value = out.get(key)
        if value:
            path = Path(value).resolve()
            try:
                rel = path.relative_to(root)
                out[key.replace("_path", "_url").replace("output_dir", "output_url")] = "/outputs/" + str(rel).replace("\\", "/")
            except ValueError:
                pass
    return out


def run(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    _load_runtime_settings()
    server = ThreadingHTTPServer((host, port), PuppetForgeHandler)
    url = f"http://{host}:{port}"
    print(f"Punch or Judy Studios running at {url}")
    print(f"Data directory: {app_data_dir()}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Puppet Forge.")
    finally:
        server.server_close()


def main() -> None:
    host = os.getenv("PUPPET_FORGE_HOST", "127.0.0.1")
    port = int(os.getenv("PUPPET_FORGE_PORT", "8765"))
    open_browser = "--no-browser" not in sys.argv
    run(host=host, port=port, open_browser=open_browser)


if __name__ == "__main__":
    main()
