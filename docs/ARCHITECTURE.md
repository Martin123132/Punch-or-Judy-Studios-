# Punch or Judy Studios Architecture

Punch or Judy Studios is local-first. The installed app can create scripts, voices, puppet animation, and render bundles without a cloud account.

## Core Modules

- `puppet_forge.storage`: SQLite schema, original cast/scene seed data, local performance memory.
- `puppet_forge.providers`: common model adapter interface for local, Ollama, OpenAI, Anthropic, Gemini, and a disabled Sora placeholder.
- `puppet_forge.prompting`: original showrunner prompt compiler, script parser, deterministic local Scriptwright fallback.
- `puppet_forge.voice`: local PuppetVoice articulated unit-bank synthesis for demo words with continuous unit-word articulation, phrase prosody, unit-word coarticulation, source/filter fallback, normalization, G2P rules, engine versioning, phoneme timing, word cues, and visemes.
- `puppet_forge.audio`: Psiren-inspired PGF cleanup, declick, clarity, warmth, normalization.
- `puppet_forge.renderer`: 2D puppet renderer, shared browser stage runtime, interactive HTML animatic, preview SVG, subtitles, script and manifest files, ZIP bundle, optional FFmpeg MP4.
- `puppet_forge.app`: dependency-free local HTTP desktop shell.

## Data Flow

1. User selects cast, scene, provider, and prompt.
2. Provider adapter returns stage-ready dialogue, or local Scriptwright does if no API/local LLM is available.
3. Performance is saved to SQLite and indexed into local memory.
4. Local PuppetVoice synthesis uses generated word units for core puppet demo words, applies phrase-level stress plus continuous internal pitch/formant/energy flow, falls back to source/filter phonemes for other words, then creates WAV audio, line cues, word cues, phoneme cues, and viseme timings.
5. Renderer creates an interactive local animatic bundle with WAV, timing, shared stage runtime, subtitles, script, manifest, preview SVG, and ZIP packaging.
6. If FFmpeg is installed, renderer also creates raster frames and exports MP4.

Audio tracks include a PuppetVoice `engine_version`. When the renderer sees an old cached track without the current engine version or phoneme cues, it generates fresh audio before exporting.

## API Boundary

External APIs are adapters only. They may generate text, and future optional render adapters may call cloud video APIs, but the product remains usable through local generation and local rendering.
