# Local Models

Punch or Judy Studios works with no API keys using the built-in Local Scriptwright. For stronger language generation, run a local OpenAI-compatible or Ollama-style model and set:

```powershell
$env:OLLAMA_HOST="http://127.0.0.1:11434"
$env:OLLAMA_MODEL="llama3"
```

Then choose `Ollama / Local` in the provider menu.

Voice and puppet rendering are local in v1. Optional downloadable voice or animation model packs can be added later without changing the core app contract.
