from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _clean_tags(values: list[str]) -> list[str]:
    return [v.strip() for v in values if v and v.strip()]


@dataclass
class VoiceProfile:
    id: str
    name: str
    base_frequency: float = 170.0
    pace: float = 1.0
    brightness: float = 0.5
    grit: float = 0.15
    warmth: float = 0.35
    formality: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PuppetRig:
    id: str
    name: str
    body_color: str
    accent_color: str
    eye_color: str = "#f7fbff"
    mouth_color: str = "#171219"
    silhouette: str = "rounded"
    scale: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Character:
    id: str
    name: str
    role: str
    lore: str
    speech_style: str
    traits: list[str] = field(default_factory=list)
    emotional_range: float = 0.7
    chaos: float = 0.25
    kindness: float = 0.65
    voice: VoiceProfile | None = None
    rig: PuppetRig | None = None

    def __post_init__(self) -> None:
        self.traits = _clean_tags(self.traits)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


@dataclass
class Scene:
    id: str
    name: str
    setting: str
    mood: str
    lighting: str = "warm theatre wash"
    camera: str = "center-stage two-shot"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PerformanceLine:
    character_id: str
    character_name: str
    text: str
    beat: str = "speak"
    emotion: str = "curious"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Performance:
    id: str
    title: str
    scene_id: str
    prompt: str
    lines: list[PerformanceLine]
    created_at: str
    provider: str = "local"
    model: str = "local-scriptwright"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "scene_id": self.scene_id,
            "prompt": self.prompt,
            "lines": [line.to_dict() for line in self.lines],
            "created_at": self.created_at,
            "provider": self.provider,
            "model": self.model,
        }


@dataclass
class AudioTrack:
    id: str
    performance_id: str
    wav_path: str
    duration_seconds: float
    visemes: list[dict[str, Any]]
    line_cues: list[dict[str, Any]] = field(default_factory=list)
    word_cues: list[dict[str, Any]] = field(default_factory=list)
    phoneme_cues: list[dict[str, Any]] = field(default_factory=list)
    engine_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RenderJob:
    id: str
    performance_id: str
    status: str
    output_dir: str
    preview_svg: str | None = None
    wav_path: str | None = None
    mp4_path: str | None = None
    html_path: str | None = None
    package_path: str | None = None
    manifest_path: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ShowProject:
    id: str
    name: str
    description: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
