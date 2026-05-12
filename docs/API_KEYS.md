# Optional API Keys

Punch or Judy Studios does not require cloud keys.

Optional text-generation keys:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GEMINI_API_KEY`

The app UI stores these in local app settings and copies them into the process environment for the current run. Local character data, performances, voices, and render outputs stay on the user's machine.

Sora/video cloud rendering is intentionally not part of the core v1 render path. The provider registry includes a disabled Sora placeholder so the optional adapter can be added later without making cloud video a dependency.
