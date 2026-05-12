# Punch or Judy Studios

Punch or Judy Studios is a local-first AI puppet show studio powered by the Puppet Forge engine. It lets people create original characters, generate dialogue with local or optional cloud models, synthesize stylized local voices, animate 2D puppets, and export a local render bundle. If FFmpeg is installed, the renderer also produces MP4.

## What Works In This V1

- Original bundled cast and scenes.
- Custom character editor with lore, speech style, personality sliders, voice pitch/pace, and puppet colors.
- Provider registry for Local Scriptwright, Ollama/local, OpenAI, Claude, Gemini, and a disabled future Sora adapter.
- Local SQLite storage in the user's app-data folder.
- Local deterministic script fallback, so no API key is required.
- Local algorithmic voice synthesis with viseme timing.
- Psiren-inspired PGF audio cleanup, warmth, clarity, declick, and normalization.
- Local 2D puppet renderer with preview SVG, subtitles, WAV, self-contained ZIP bundles, and optional FFmpeg MP4.
- Windows-first launcher: double-click `START_HERE_WINDOWS.bat`.

## Quick Start

```powershell
cd C:\Users\ollet\OneDrive\Documents\Punch-or-Judy-Studios-
python -m puppet_forge.app
```

Then open:

```text
http://127.0.0.1:8765
```

On Windows, double-click `START_HERE_WINDOWS.bat`.

## Local-First Promise

The creative/runtime core is ours: characters, prompts, puppet rigs, voice logic, audio cleanup, stage renderer, timeline, and UX. Open-source infrastructure is used only for normal app/runtime needs. External AI APIs are optional text adapters, not the product's foundation.

## Optional MP4 Export

Install FFmpeg and make sure `ffmpeg` is on PATH. Without FFmpeg, the app still exports a local bundle with:

- `preview.svg`
- `index.html`
- `subtitles.vtt`
- `script.txt`
- `manifest.json`
- generated `.wav`
- zipped self-contained package

When FFmpeg is available, frame generation is enabled for MP4 export. Without FFmpeg, the app skips heavy frame dumps and writes a faster interactive animatic bundle instead.

## Development

Run tests:

```powershell
python -m unittest discover -s tests
```

Run the smoke pipeline:

```powershell
python scripts\smoke_pipeline.py
```

See `docs/ARCHITECTURE.md`, `docs/LOCAL_MODELS.md`, and `docs/API_KEYS.md`.
