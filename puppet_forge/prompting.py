from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from .models import Performance, PerformanceLine


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return cleaned or uuid.uuid4().hex[:8]


def build_system_prompt(characters: list[dict[str, Any]], scene: dict[str, Any], memory: list[dict[str, Any]] | None = None) -> str:
    cast = []
    for character in characters:
        traits = ", ".join(character.get("traits") or [])
        cast.append(
            f"- {character['name']} ({character['role']}): lore={character['lore']}; "
            f"speech_style={character['speech_style']}; traits={traits}; "
            f"kindness={character.get('kindness', 0.5)} chaos={character.get('chaos', 0.2)}"
        )
    memory_text = ""
    if memory:
        memory_text = "\nRelevant local memory:\n" + "\n".join(
            f"- {m.get('character_name', 'Memory')}: {m.get('snippet', '')}" for m in memory[:6]
        )
    return (
        "You are Puppet Forge's original showrunner. Write only original dialogue for the provided cast. "
        "Return stage-ready lines with one speaker per line in the form `Name: dialogue`. "
        "Do not copy public fictional characters, celebrities, or copyrighted catchphrases. "
        "Keep each line performable by a 2D puppet and add clear emotional beats inside the dialogue, not markup.\n\n"
        f"Scene: {scene.get('name', 'Stage')}\n"
        f"Setting: {scene.get('setting', '')}\n"
        f"Mood: {scene.get('mood', '')}\n"
        f"Lighting: {scene.get('lighting', '')}\n\n"
        "Cast:\n"
        + "\n".join(cast)
        + memory_text
    )


def parse_script(text: str, characters: list[dict[str, Any]]) -> list[PerformanceLine]:
    by_name = {c["name"].lower(): c for c in characters}
    fallback = characters[0] if characters else {"id": "narrator", "name": "Narrator"}
    lines: list[PerformanceLine] = []
    for raw in text.splitlines():
        line = raw.strip().strip("-").strip()
        if not line:
            continue
        speaker = fallback["name"]
        spoken = line
        if ":" in line:
            maybe_speaker, maybe_text = line.split(":", 1)
            if maybe_speaker.strip().lower() in by_name:
                speaker = maybe_speaker.strip()
                spoken = maybe_text.strip()
        character = by_name.get(speaker.lower(), fallback)
        emotion = infer_emotion(spoken)
        lines.append(
            PerformanceLine(
                character_id=character["id"],
                character_name=character["name"],
                text=spoken,
                beat="speak",
                emotion=emotion,
            )
        )
    return lines


def infer_emotion(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ["?", "wonder", "maybe", "curious", "what if"]):
        return "curious"
    if any(word in lowered for word in ["great", "brilliant", "yes", "spark", "show"]):
        return "bright"
    if any(word in lowered for word in ["careful", "wait", "hmm", "shadow", "quiet"]):
        return "careful"
    if any(word in lowered for word in ["laugh", "wild", "dance", "boom"]):
        return "playful"
    return "steady"


def local_scriptwright(prompt: str, characters: list[dict[str, Any]], scene: dict[str, Any], memory: list[dict[str, Any]] | None = None) -> str:
    """A deterministic local fallback script engine.

    This is intentionally original and local. It gives users something useful even
    with no AI API key or local LLM running.
    """
    if not characters:
        return "Narrator: The stage is awake, but no cast has stepped into the light yet."

    prompt_clean = prompt.strip().rstrip(".!?")
    seed = int(hashlib.sha256((prompt + scene.get("id", "")).encode("utf-8")).hexdigest()[:8], 16)
    beats = [
        "sets the stakes",
        "twists the idea sideways",
        "grounds it in a concrete action",
        "turns the tune into motion",
        "lands the show with a choice",
    ]
    tone_words = ["glimmer", "pulse", "thread", "cue", "spark", "hinge", "echo", "lantern"]
    memory_hint = ""
    if memory:
        memory_hint = " I remember a useful earlier clue: " + memory[0].get("snippet", "").replace("[", "").replace("]", "")
    lines = []
    for idx in range(6):
        character = characters[(idx + seed) % len(characters)]
        beat = beats[idx % len(beats)]
        word = tone_words[(seed + idx * 3) % len(tone_words)]
        style = character.get("speech_style", "clear and performable").split(",")[0]
        if idx == 0:
            text = f"I hear the request: {prompt_clean}. Let us make it visible, not just clever."
        elif idx == 1:
            text = f"The {word} of it is this: the {scene.get('mood', 'stage')} mood needs a body, a voice, and a rhythm."
        elif idx == 2:
            text = f"My part {beat}: I will turn the idea into one playable cue the audience can feel."
        elif idx == 3:
            text = f"Give the puppet a small want, then let every line tug that want across the stage."
        elif idx == 4:
            text = f"Sound first, motion second, silence third. That is how the scene breathes.{memory_hint}"
        else:
            text = "Curtain note: keep the machinery local, keep the characters ours, and let the show dance."
        lines.append(f"{character['name']}: {text} ({style})")
    return "\n".join(lines)


def make_performance(
    *,
    prompt: str,
    script: str,
    characters: list[dict[str, Any]],
    scene: dict[str, Any],
    provider: str,
    model: str,
) -> Performance:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    title = prompt.strip()[:60] or "Untitled Show"
    perf_id = f"perf-{slugify(title)}-{uuid.uuid4().hex[:6]}"
    lines = parse_script(script, characters)
    if not lines:
        lines = parse_script(local_scriptwright(prompt, characters, scene), characters)
    return Performance(
        id=perf_id,
        title=title,
        scene_id=scene["id"],
        prompt=prompt,
        lines=lines,
        created_at=now,
        provider=provider,
        model=model,
    )
