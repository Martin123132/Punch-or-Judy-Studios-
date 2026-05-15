# Punch or Judy Studios

Punch or Judy Studios is a local-first AI puppet show studio powered by the Puppet Forge engine. It lets people create original characters, generate dialogue with local or optional cloud models, synthesize stylized local voices, animate 2D puppets, and export a local render bundle. If FFmpeg is installed, the renderer also produces MP4.

## What Works In This V0.11

- Original bundled cast and scenes.
- Custom character editor with lore, speech style, personality sliders, voice pitch/pace, and puppet colors.
- One-click `Run Show` flow from prompt to script, local voice, synced puppet playback, and export bundle.
- Provider registry for Local Scriptwright, Ollama/local, OpenAI, Claude, Gemini, and a disabled future Sora adapter.
- Local SQLite storage in the user's app-data folder.
- Local deterministic script fallback, so no API key is required.
- Local PuppetVoice v0.11 articulated synthesis for the core puppet demo phrases and normal generated words, now with continuous unit-word articulation, continuous fallback-word articulation, stronger English-like pronunciation rules, smoother pitch/formant/energy flow, phrase prosody, punctuation pauses, line cues, word cues, phoneme cues, visemes, and engine-versioned audio regeneration.
- Psiren-inspired PGF audio cleanup, warmth, clarity, declick, and normalization.
- Local 2D puppet renderer with speaker spotlights, blink/gaze/gesture motion, preview SVG, subtitles, WAV, self-contained ZIP bundles, and optional FFmpeg MP4.
- Windows-first launcher: double-click `START_HERE_WINDOWS.bat`.

## Quick Start

```powershell
git clone https://github.com/Martin123132/Punch-or-Judy-Studios-.git
cd Punch-or-Judy-Studios-
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
- `stage.js`
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

Generate local voice audition WAVs:

```powershell
python scripts\audition_voice.py
```

The audition harness writes per-character WAVs plus a manifest with phoneme transcripts, timing cues, peak, RMS, and duration metrics.

See `docs/ARCHITECTURE.md`, `docs/LOCAL_MODELS.md`, and `docs/API_KEYS.md`.
