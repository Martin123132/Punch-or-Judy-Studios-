from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .prompting import build_system_prompt, local_scriptwright


class ProviderError(RuntimeError):
    pass


def _json_post(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None, timeout: int = 90) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"content-type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ProviderError(f"{exc.code} {body}") from exc
    except OSError as exc:
        raise ProviderError(str(exc)) from exc


def available_providers() -> list[dict[str, Any]]:
    return [
        {
            "id": "local",
            "name": "Local Scriptwright",
            "needs_key": False,
            "models": ["local-scriptwright"],
            "description": "Deterministic built-in script generation. No network, no key.",
        },
        {
            "id": "ollama",
            "name": "Ollama / Local",
            "needs_key": False,
            "models": [os.getenv("OLLAMA_MODEL", "llama3")],
            "description": "Local model through Ollama's chat endpoint.",
        },
        {
            "id": "openai",
            "name": "OpenAI",
            "needs_key": True,
            "models": [os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o-mini")],
            "description": "Optional cloud text generation adapter.",
        },
        {
            "id": "anthropic",
            "name": "Claude",
            "needs_key": True,
            "models": [os.getenv("ANTHROPIC_MODEL_DEFAULT", "claude-3-5-sonnet-20241022")],
            "description": "Optional Claude text generation adapter.",
        },
        {
            "id": "gemini",
            "name": "Gemini",
            "needs_key": True,
            "models": [os.getenv("GEMINI_MODEL_DEFAULT", "gemini-1.5-flash")],
            "description": "Optional Gemini text generation adapter.",
        },
        {
            "id": "sora",
            "name": "Sora Video API",
            "needs_key": True,
            "models": ["sora-2", "sora-2-pro"],
            "description": "Future optional cloud render adapter; local renderer remains primary.",
            "disabled": True,
        },
    ]


def generate(
    *,
    provider: str,
    model: str | None,
    prompt: str,
    characters: list[dict[str, Any]],
    scene: dict[str, Any],
    memory: list[dict[str, Any]] | None = None,
    temperature: float = 0.7,
) -> dict[str, str]:
    provider = (provider or "local").strip().lower()
    model = model or default_model(provider)
    system_prompt = build_system_prompt(characters, scene, memory)
    if provider == "local":
        return {
            "provider": "local",
            "model": "local-scriptwright",
            "script": local_scriptwright(prompt, characters, scene, memory),
        }
    if provider == "ollama":
        script = _ollama(model, system_prompt, prompt, temperature)
    elif provider == "openai":
        script = _openai(model, system_prompt, prompt, temperature)
    elif provider == "anthropic":
        script = _anthropic(model, system_prompt, prompt, temperature)
    elif provider == "gemini":
        script = _gemini(model, system_prompt, prompt, temperature)
    else:
        raise ProviderError(f"Unsupported provider '{provider}'.")
    return {"provider": provider, "model": model, "script": script}


def default_model(provider: str) -> str:
    for item in available_providers():
        if item["id"] == provider:
            return item["models"][0]
    return "local-scriptwright"


def _ollama(model: str, system_prompt: str, prompt: str, temperature: float) -> str:
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": max(0.0, min(temperature, 1.0))},
    }
    data = _json_post(f"{host}/api/chat", payload, timeout=120)
    message = data.get("message") or {}
    return str(message.get("content") or data.get("response") or "").strip()


def _openai(model: str, system_prompt: str, prompt: str, temperature: float) -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ProviderError("OPENAI_API_KEY is not set.")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": max(0.0, min(temperature, 1.0)),
    }
    data = _json_post(
        "https://api.openai.com/v1/chat/completions",
        payload,
        headers={"authorization": f"Bearer {key}"},
    )
    return str(data["choices"][0]["message"].get("content") or "").strip()


def _anthropic(model: str, system_prompt: str, prompt: str, temperature: float) -> str:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise ProviderError("ANTHROPIC_API_KEY is not set.")
    payload = {
        "model": model,
        "system": system_prompt,
        "max_tokens": 1200,
        "temperature": max(0.0, min(temperature, 1.0)),
        "messages": [{"role": "user", "content": prompt}],
    }
    data = _json_post(
        "https://api.anthropic.com/v1/messages",
        payload,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    blocks = data.get("content") or []
    return "\n".join(str(block.get("text", "")) for block in blocks if isinstance(block, dict)).strip()


def _gemini(model: str, system_prompt: str, prompt: str, temperature: float) -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ProviderError("GEMINI_API_KEY is not set.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": max(0.0, min(temperature, 1.0))},
    }
    data = _json_post(url, payload)
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    return "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict)).strip()

