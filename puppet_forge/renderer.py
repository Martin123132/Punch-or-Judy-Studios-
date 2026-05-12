from __future__ import annotations

import html
import json
import math
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path
from typing import Any

from .models import RenderJob
from .paths import render_dir, repo_root


WIDTH = 640
HEIGHT = 360


def _hex_to_rgb(value: str, fallback: tuple[int, int, int] = (180, 120, 80)) -> tuple[int, int, int]:
    value = (value or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        return fallback
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return fallback


def _write_ppm(path: Path, pixels: bytearray) -> None:
    with path.open("wb") as fh:
        fh.write(f"P6\n{WIDTH} {HEIGHT}\n255\n".encode("ascii"))
        fh.write(pixels)


def _new_stage(scene: dict[str, Any]) -> bytearray:
    mood = (scene.get("mood") or "").lower()
    if "night" in mood or "quiet" in mood:
        top = (18, 28, 52)
        bottom = (48, 38, 54)
    else:
        top = (32, 30, 38)
        bottom = (72, 48, 34)
    pixels = bytearray(WIDTH * HEIGHT * 3)
    for y in range(HEIGHT):
        ratio = y / max(1, HEIGHT - 1)
        r = int(top[0] * (1 - ratio) + bottom[0] * ratio)
        g = int(top[1] * (1 - ratio) + bottom[1] * ratio)
        b = int(top[2] * (1 - ratio) + bottom[2] * ratio)
        for x in range(WIDTH):
            idx = (y * WIDTH + x) * 3
            vignette = 1.0 - min(0.42, ((x - WIDTH / 2) ** 2 / (WIDTH * WIDTH) + (y - HEIGHT / 2) ** 2 / (HEIGHT * HEIGHT)) * 1.2)
            pixels[idx] = int(r * vignette)
            pixels[idx + 1] = int(g * vignette)
            pixels[idx + 2] = int(b * vignette)
    # Stage floor.
    for y in range(int(HEIGHT * 0.72), HEIGHT):
        shade = int(46 + (y - HEIGHT * 0.72) * 0.15)
        for x in range(WIDTH):
            idx = (y * WIDTH + x) * 3
            pixels[idx] = min(255, pixels[idx] + shade)
            pixels[idx + 1] = min(255, pixels[idx + 1] + shade // 2)
            pixels[idx + 2] = min(255, pixels[idx + 2] + 16)
    return pixels


def _blend(pixels: bytearray, x: int, y: int, color: tuple[int, int, int], alpha: float = 1.0) -> None:
    if x < 0 or y < 0 or x >= WIDTH or y >= HEIGHT:
        return
    idx = (y * WIDTH + x) * 3
    inv = 1.0 - alpha
    pixels[idx] = int(pixels[idx] * inv + color[0] * alpha)
    pixels[idx + 1] = int(pixels[idx + 1] * inv + color[1] * alpha)
    pixels[idx + 2] = int(pixels[idx + 2] * inv + color[2] * alpha)


def _ellipse(
    pixels: bytearray,
    cx: int,
    cy: int,
    rx: int,
    ry: int,
    color: tuple[int, int, int],
    alpha: float = 1.0,
) -> None:
    min_x = max(0, cx - rx)
    max_x = min(WIDTH - 1, cx + rx)
    min_y = max(0, cy - ry)
    max_y = min(HEIGHT - 1, cy + ry)
    rx_sq = max(1, rx * rx)
    ry_sq = max(1, ry * ry)
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            dx = x - cx
            dy = y - cy
            if dx * dx / rx_sq + dy * dy / ry_sq <= 1.0:
                _blend(pixels, x, y, color, alpha)


def _rect(pixels: bytearray, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int], alpha: float = 1.0) -> None:
    for y in range(max(0, y0), min(HEIGHT, y1)):
        for x in range(max(0, x0), min(WIDTH, x1)):
            _blend(pixels, x, y, color, alpha)


def _active_viseme(visemes: list[dict[str, Any]], character_id: str, t: float) -> str:
    for event in visemes:
        if event.get("character_id") == character_id and float(event.get("start", 0)) <= t <= float(event.get("end", 0)):
            return str(event.get("viseme", "rest"))
    return "rest"


def _draw_puppet(
    pixels: bytearray,
    character: dict[str, Any],
    x: int,
    y: int,
    scale: float,
    t: float,
    viseme: str,
    side: int,
) -> None:
    rig = character.get("rig") or {}
    body = _hex_to_rgb(rig.get("body_color", "#b85f37"))
    accent = _hex_to_rgb(rig.get("accent_color", "#ffd166"))
    eye = _hex_to_rgb(rig.get("eye_color", "#f7fbff"), (248, 248, 248))
    mouth = _hex_to_rgb(rig.get("mouth_color", "#171219"), (18, 12, 16))
    bob = int(math.sin(t * 4.0 + side) * 6)
    sway = int(math.sin(t * 2.2 + side) * 8)
    x += sway
    y += bob
    s = scale
    # shadow, strings, body, head
    _ellipse(pixels, x, y + int(166 * s), int(86 * s), int(18 * s), (8, 6, 10), 0.32)
    _rect(pixels, x - int(2 * s), 42, x + int(2 * s), y - int(86 * s), accent, 0.55)
    _ellipse(pixels, x, y + int(80 * s), int(74 * s), int(98 * s), body, 1.0)
    _ellipse(pixels, x, y - int(38 * s), int(72 * s), int(66 * s), body, 1.0)
    _ellipse(pixels, x - int(20 * s), y - int(78 * s), int(24 * s), int(16 * s), accent, 0.9)
    _ellipse(pixels, x + int(20 * s), y - int(78 * s), int(24 * s), int(16 * s), accent, 0.9)
    # eyes
    _ellipse(pixels, x - int(24 * s), y - int(48 * s), int(12 * s), int(16 * s), eye, 1.0)
    _ellipse(pixels, x + int(24 * s), y - int(48 * s), int(12 * s), int(16 * s), eye, 1.0)
    look = int(math.sin(t * 3.0) * 3)
    _ellipse(pixels, x - int(24 * s) + look, y - int(46 * s), int(5 * s), int(7 * s), (12, 14, 20), 1.0)
    _ellipse(pixels, x + int(24 * s) + look, y - int(46 * s), int(5 * s), int(7 * s), (12, 14, 20), 1.0)
    # mouth shapes from viseme timing
    if viseme == "closed":
        _rect(pixels, x - int(22 * s), y - int(12 * s), x + int(22 * s), y - int(6 * s), mouth, 1.0)
    elif viseme == "wide":
        _ellipse(pixels, x, y - int(8 * s), int(34 * s), int(10 * s), mouth, 1.0)
    elif viseme == "round":
        _ellipse(pixels, x, y - int(8 * s), int(17 * s), int(22 * s), mouth, 1.0)
    elif viseme == "open":
        _ellipse(pixels, x, y - int(8 * s), int(25 * s), int(28 * s), mouth, 1.0)
    elif viseme == "teeth":
        _ellipse(pixels, x, y - int(8 * s), int(28 * s), int(13 * s), mouth, 1.0)
        _rect(pixels, x - int(20 * s), y - int(14 * s), x + int(20 * s), y - int(8 * s), (245, 238, 220), 0.95)
    else:
        _ellipse(pixels, x, y - int(8 * s), int(22 * s), int(6 * s), mouth, 0.85)
    # arms
    _ellipse(pixels, x - int(78 * s), y + int(36 * s), int(22 * s), int(48 * s), body, 1.0)
    _ellipse(pixels, x + int(78 * s), y + int(36 * s), int(22 * s), int(48 * s), body, 1.0)
    _ellipse(pixels, x - int(82 * s), y + int(82 * s), int(18 * s), int(16 * s), accent, 1.0)
    _ellipse(pixels, x + int(82 * s), y + int(82 * s), int(18 * s), int(16 * s), accent, 1.0)


def _frame(path: Path, characters: list[dict[str, Any]], scene: dict[str, Any], visemes: list[dict[str, Any]], t: float) -> None:
    pixels = _new_stage(scene)
    # overhead lights
    _ellipse(pixels, 210, 140, 130, 220, (255, 214, 142), 0.08)
    _ellipse(pixels, 430, 140, 130, 220, (118, 201, 232), 0.06)
    cast = characters[:3]
    positions = [(220, 212), (420, 212), (320, 222)]
    for idx, character in enumerate(cast):
        viseme = _active_viseme(visemes, character["id"], t)
        scale = 0.56 if idx < 2 else 0.5
        _draw_puppet(pixels, character, positions[idx][0], positions[idx][1], scale, t, viseme, idx)
    _write_ppm(path, pixels)


def write_preview_svg(path: Path, characters: list[dict[str, Any]], scene: dict[str, Any]) -> None:
    cast = characters[:3]
    bg = "#211f26" if "night" not in (scene.get("mood") or "").lower() else "#111c34"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}">',
        f'<rect width="100%" height="100%" fill="{bg}"/>',
        '<ellipse cx="210" cy="165" rx="140" ry="230" fill="#ffd68e" opacity=".12"/>',
        '<ellipse cx="430" cy="165" rx="140" ry="230" fill="#78c9e8" opacity=".1"/>',
        '<rect y="258" width="640" height="102" fill="#5a3928"/>',
    ]
    positions = [(220, 212), (420, 212), (320, 222)]
    for idx, character in enumerate(cast):
        rig = character.get("rig") or {}
        x, y = positions[idx]
        s = 0.56 if idx < 2 else 0.5
        body = html.escape(rig.get("body_color", "#b85f37"))
        accent = html.escape(rig.get("accent_color", "#ffd166"))
        mouth = html.escape(rig.get("mouth_color", "#171219"))
        parts.extend(
            [
                f'<ellipse cx="{x}" cy="{y + 142*s}" rx="{82*s}" ry="{18*s}" fill="#08060a" opacity=".32"/>',
                f'<line x1="{x}" y1="44" x2="{x}" y2="{y-80*s}" stroke="{accent}" stroke-width="4" opacity=".6"/>',
                f'<ellipse cx="{x}" cy="{y+80*s}" rx="{74*s}" ry="{98*s}" fill="{body}"/>',
                f'<ellipse cx="{x}" cy="{y-38*s}" rx="{72*s}" ry="{66*s}" fill="{body}"/>',
                f'<ellipse cx="{x-24*s}" cy="{y-48*s}" rx="{12*s}" ry="{16*s}" fill="#f8fbff"/>',
                f'<ellipse cx="{x+24*s}" cy="{y-48*s}" rx="{12*s}" ry="{16*s}" fill="#f8fbff"/>',
                f'<ellipse cx="{x-23*s}" cy="{y-46*s}" rx="{5*s}" ry="{7*s}" fill="#0c0e14"/>',
                f'<ellipse cx="{x+25*s}" cy="{y-46*s}" rx="{5*s}" ry="{7*s}" fill="#0c0e14"/>',
                f'<ellipse cx="{x}" cy="{y-8*s}" rx="{24*s}" ry="{16*s}" fill="{mouth}"/>',
                f'<text x="{x}" y="{y+190*s}" text-anchor="middle" fill="#fff5dd" font-family="Segoe UI, sans-serif" font-size="24" font-weight="700">{html.escape(character["name"])}</text>',
            ]
        )
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_subtitles(path: Path, performance: dict[str, Any], duration: float, line_cues: list[dict[str, Any]] | None = None) -> None:
    lines = performance.get("lines", [])
    cues = line_cues or []
    segment = duration / max(1, len(lines))

    def stamp(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h:02}:{m:02}:{s:06.3f}"

    out = ["WEBVTT", ""]
    for idx, line in enumerate(lines):
        cue = cues[idx] if idx < len(cues) else {}
        start = float(cue.get("start", idx * segment))
        end = float(cue.get("end", min(duration, (idx + 1) * segment)))
        out.append(f"{stamp(start)} --> {stamp(end)}")
        out.append(f"{line['character_name']}: {line['text']}")
        out.append("")
    path.write_text("\n".join(out), encoding="utf-8")


def write_script_text(path: Path, performance: dict[str, Any]) -> None:
    lines = [performance.get("title", "Puppet Forge Render"), ""]
    for line in performance.get("lines", []):
        lines.append(f"{line['character_name']}: {line['text']}")
    path.write_text("\n".join(lines), encoding="utf-8")


def _cast_payload(characters: list[dict[str, Any]], performance: dict[str, Any]) -> list[dict[str, Any]]:
    ids: list[str] = []
    for line in performance.get("lines", []):
        character_id = line.get("character_id")
        if character_id and character_id not in ids:
            ids.append(character_id)
    if not ids:
        ids = [character.get("id") for character in characters[:3] if character.get("id")]
    by_id = {character.get("id"): character for character in characters}
    cast: list[dict[str, Any]] = []
    for character_id in ids[:3]:
        character = by_id.get(character_id)
        if character:
            cast.append(
                {
                    "id": character.get("id"),
                    "name": character.get("name"),
                    "role": character.get("role"),
                    "rig": character.get("rig") or {},
                    "voice": character.get("voice") or {},
                }
            )
    return cast


def _performance_characters(characters: list[dict[str, Any]], performance: dict[str, Any]) -> list[dict[str, Any]]:
    ids: list[str] = []
    for line in performance.get("lines", []):
        character_id = line.get("character_id")
        if character_id and character_id not in ids:
            ids.append(character_id)
    by_id = {character.get("id"): character for character in characters}
    selected = [by_id[item] for item in ids if item in by_id]
    return selected[:3] or characters[:3]


def _stage_style(scene: dict[str, Any]) -> dict[str, Any]:
    mood = f"{scene.get('mood', '')} {scene.get('lighting', '')}".lower()
    night = "night" in mood or "quiet" in mood or "moon" in mood
    return {
        "renderer": "local-2d-puppet-stage",
        "width": WIDTH,
        "height": HEIGHT,
        "mood": scene.get("mood", "curious"),
        "lighting": scene.get("lighting", "warm theatre wash"),
        "camera": scene.get("camera", "center-stage two-shot"),
        "palette": "moonlit" if night else "workshop",
    }


def _motion_cues(audio_track: dict[str, Any]) -> dict[str, Any]:
    return {
        "timing_source": "audio-time",
        "mouth_sync": "visemes",
        "speaker_focus": "line_cues",
        "gesture_source": "word_cues",
        "blink_cycle_seconds": 4.8,
        "line_count": len(audio_track.get("line_cues") or []),
        "word_count": len(audio_track.get("word_cues") or []),
        "phoneme_count": len(audio_track.get("phoneme_cues") or []),
        "engine_version": audio_track.get("engine_version", ""),
    }


def write_manifest(
    path: Path,
    performance: dict[str, Any],
    characters: list[dict[str, Any]],
    scene: dict[str, Any],
    audio_track: dict[str, Any],
    render_job: RenderJob,
) -> None:
    payload = {
        "format": "puppet-forge-render-bundle",
        "version": 2,
        "performance": performance,
        "cast": _cast_payload(characters, performance),
        "scene": scene,
        "stage_style": _stage_style(scene),
        "motion_cues": _motion_cues(audio_track),
        "audio": {
            "engine_version": audio_track.get("engine_version", ""),
            "duration_seconds": audio_track.get("duration_seconds"),
            "wav": Path(str(audio_track.get("wav_path", ""))).name,
            "line_cues": audio_track.get("line_cues") or [],
            "word_cues": audio_track.get("word_cues") or [],
            "phoneme_count": len(audio_track.get("phoneme_cues") or []),
            "phoneme_cues": audio_track.get("phoneme_cues") or [],
            "viseme_count": len(audio_track.get("visemes") or []),
            "visemes": audio_track.get("visemes") or [],
        },
        "render": render_job.to_dict(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_preview_html(
    path: Path,
    performance: dict[str, Any],
    characters: list[dict[str, Any]],
    scene: dict[str, Any],
    audio_track: dict[str, Any],
    render_job: RenderJob,
) -> None:
    data = {
        "characters": _cast_payload(characters, performance),
        "performance": performance,
        "scene": scene,
        "audio": {
            "engine_version": audio_track.get("engine_version", ""),
            "duration_seconds": audio_track.get("duration_seconds"),
            "line_cues": audio_track.get("line_cues") or [],
            "word_cues": audio_track.get("word_cues") or [],
            "phoneme_cues": audio_track.get("phoneme_cues") or [],
            "visemes": audio_track.get("visemes") or [],
        },
        "render": render_job.to_dict(),
    }
    data_text = html.escape(json.dumps(data), quote=False)
    mp4_link = (
        f'<a href="{html.escape(Path(render_job.mp4_path).name)}">MP4</a>'
        if render_job.mp4_path
        else ""
    )
    html_text = f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(performance.get("title", "Puppet Forge Render"))}</title>
<style>
:root {{ color-scheme: dark; --bg: #15171c; --panel: #20242d; --line: #303644; --text: #f6f1e8; --muted: #aab3c2; --gold: #f3b75f; --teal: #68c3c0; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 Segoe UI, Arial, sans-serif; letter-spacing: 0; }}
main {{ max-width: 1120px; margin: 0 auto; padding: 28px; }}
h1 {{ margin: 0 0 6px; font-size: clamp(24px, 4vw, 40px); line-height: 1.05; }}
.meta {{ color: var(--muted); margin: 0 0 18px; }}
.stage {{ width: 100%; border-radius: 8px; overflow: hidden; background: #151824; border: 1px solid var(--line); box-shadow: 0 20px 80px #0008; }}
canvas {{ width: 100%; display: block; aspect-ratio: {WIDTH} / {HEIGHT}; background: #151824; }}
audio {{ width: 100%; margin: 16px 0 8px; }}
.status {{ color: var(--muted); margin: 0 0 16px; }}
.exports {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0; }}
.exports a {{ border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; color: #9bd6ff; text-decoration: none; background: #20242d; }}
.line {{ display: grid; grid-template-columns: minmax(110px, 150px) 1fr; gap: 12px; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; margin: 8px 0; background: var(--panel); }}
.line strong {{ color: var(--gold); }}
.line.active {{ border-color: var(--gold); background: #2a3039; box-shadow: inset 4px 0 0 var(--gold); }}
.word {{ color: var(--teal); min-height: 22px; }}
@media (max-width: 680px) {{ main {{ padding: 16px; }} .line {{ grid-template-columns: 1fr; }} }}
</style>
<main>
  <h1>{html.escape(performance.get("title", "Puppet Forge Render"))}</h1>
  <p class="meta">Interactive local animatic generated on this machine.</p>
  <div class="stage"><canvas id="stage" width="{WIDTH}" height="{HEIGHT}"></canvas></div>
  <audio id="showAudio" controls src="{html.escape(Path(render_job.wav_path or '').name)}"></audio>
  <p id="activeWord" class="word"></p>
  <p class="status">Status: {html.escape(render_job.status)}. {html.escape(render_job.message)}</p>
  <div class="exports">
    <a href="{html.escape(Path(render_job.preview_svg or '').name)}">Stage SVG</a>
    <a href="{html.escape(Path(render_job.wav_path or '').name)}">WAV</a>
    {mp4_link}
    <a href="subtitles.vtt">Subtitles</a>
    <a href="script.txt">Script</a>
    <a href="manifest.json">Manifest</a>
    <a href="{html.escape(Path(render_job.package_path or '').name)}">ZIP Package</a>
  </div>
  <div id="script"></div>
</main>
<script id="show-data" type="application/json">{data_text}</script>
<script src="stage.js"></script>
<script>
const data = JSON.parse(document.getElementById('show-data').textContent);
const script = document.getElementById('script');
const activeWord = document.getElementById('activeWord');
script.innerHTML = data.performance.lines.map((line, index) =>
  `<div class="line" data-line-index="${{index}}"><strong>${{line.character_name}}</strong><span>${{line.text}}</span></div>`
).join('');
const stage = window.PuppetStage.create(document.getElementById('stage'), {{
  onFrame(frame) {{
    document.querySelectorAll('.line').forEach((element) => {{
      element.classList.toggle('active', Boolean(frame.activeLine && Number(element.dataset.lineIndex) === frame.activeLine.index));
    }});
    activeWord.textContent = frame.activeWord ? `${{frame.activeWord.character_name}}: ${{frame.activeWord.word}}` : '';
  }}
}});
const audio = document.getElementById('showAudio');
stage.setAudioElement(audio);
stage.setShow(data);
</script>
</html>"""
    path.write_text(html_text, encoding="utf-8")


def package_bundle(path: Path, out_dir: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in out_dir.rglob("*"):
            if item.is_file() and item != path:
                archive.write(item, item.relative_to(out_dir))


def render_performance(
    performance: dict[str, Any],
    characters: list[dict[str, Any]],
    scene: dict[str, Any],
    audio_track: dict[str, Any],
    fps: int = 8,
) -> RenderJob:
    render_id = f"render-{uuid.uuid4().hex[:8]}"
    out_dir = render_dir(render_id)
    render_characters = _performance_characters(characters, performance)
    preview_svg = out_dir / "preview.svg"
    write_preview_svg(preview_svg, render_characters, scene)
    stage_runtime = repo_root() / "puppet_forge" / "static" / "stage.js"
    if stage_runtime.exists():
        shutil.copy2(stage_runtime, out_dir / "stage.js")
    source_wav = Path(str(audio_track.get("wav_path", "")))
    bundled_wav = out_dir / source_wav.name
    if source_wav.exists() and source_wav.resolve() != bundled_wav.resolve():
        shutil.copy2(source_wav, bundled_wav)
    else:
        bundled_wav = source_wav
    duration = float(audio_track.get("duration_seconds") or 1.0)
    line_cues = audio_track.get("line_cues") or []
    write_subtitles(out_dir / "subtitles.vtt", performance, duration, line_cues)
    write_script_text(out_dir / "script.txt", performance)

    job = RenderJob(
        id=render_id,
        performance_id=performance["id"],
        status="bundle-ready",
        output_dir=str(out_dir),
        preview_svg=str(preview_svg),
        wav_path=str(bundled_wav),
        message="Exported local animatic preview, subtitles, audio, script, and manifest.",
    )
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        frame_count = max(1, min(120, int(duration * fps)))
        frame_dir = out_dir / "frames"
        frame_dir.mkdir(exist_ok=True)
        visemes = audio_track.get("visemes") or []
        for i in range(frame_count):
            _frame(frame_dir / f"frame_{i:04d}.ppm", render_characters, scene, visemes, i / fps)
        mp4 = out_dir / f"{render_id}.mp4"
        command = [
            ffmpeg,
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frame_dir / "frame_%04d.ppm"),
            "-i",
            str(audio_track["wav_path"]),
            "-shortest",
            "-pix_fmt",
            "yuv420p",
            str(mp4),
        ]
        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            job.status = "mp4-ready"
            job.mp4_path = str(mp4)
            job.message = "MP4 exported with local renderer and FFmpeg."
        except Exception as exc:
            job.status = "bundle-ready"
            job.message = f"FFmpeg was found but MP4 export failed; local bundle is ready. {exc}"
    else:
        job.message = "FFmpeg is not installed, so MP4 was skipped; the fast local bundle includes an interactive HTML animatic, WAV, subtitles, SVG, script, and manifest."
    preview_html = out_dir / "index.html"
    job.html_path = str(preview_html)
    manifest_path = out_dir / "manifest.json"
    job.manifest_path = str(manifest_path)
    package_path = out_dir / f"{render_id}.zip"
    job.package_path = str(package_path)
    write_manifest(manifest_path, performance, render_characters, scene, audio_track, job)
    write_preview_html(preview_html, performance, render_characters, scene, audio_track, job)
    package_bundle(package_path, out_dir)
    return job
