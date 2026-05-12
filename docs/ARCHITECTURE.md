# Punch or Judy Studios Architecture

Punch or Judy Studios is local-first. The installed app can create scripts, voices, puppet animation, and render bundles without a cloud account.

## Core Modules

- `puppet_forge.storage`: SQLite schema, original cast/scene seed data, local performance memory.
- `puppet_forge.providers`: common model adapter interface for local, Ollama, OpenAI, Anthropic, Gemini, and a disabled Sora placeholder.
- `puppet_forge.prompting`: original showrunner prompt compiler, script parser, deterministic local Scriptwright fallback.
- `puppet_forge.voice`: local stylized speech synthesis and viseme timing.
- `puppet_forge.audio`: Psiren-inspired PGF cleanup, declick, clarity, warmth, normalization.
- `puppet_forge.renderer`: 2D puppet renderer, interactive HTML animatic, preview SVG, subtitles, script and manifest files, ZIP bundle, optional FFmpeg MP4.
- `puppet_forge.app`: dependency-free local HTTP desktop shell.

## Data Flow

1. User selects cast, scene, provider, and prompt.
2. Provider adapter returns stage-ready dialogue, or local Scriptwright does if no API/local LLM is available.
3. Performance is saved to SQLite and indexed into local memory.
4. Local voice synthesis creates WAV audio and viseme timings.
5. Renderer creates an interactive local animatic bundle with WAV, timing, subtitles, script, manifest, preview SVG, and ZIP packaging.
6. If FFmpeg is installed, renderer also creates raster frames and exports MP4.

## API Boundary

External APIs are adapters only. They may generate text, and future optional render adapters may call cloud video APIs, but the product remains usable through local generation and local rendering.
