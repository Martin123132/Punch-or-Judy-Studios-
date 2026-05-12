from __future__ import annotations

from .models import Character, PuppetRig, Scene, VoiceProfile


DEFAULT_VOICES = [
    VoiceProfile("emberalto", "Ember Alto", base_frequency=185, pace=0.96, brightness=0.68, grit=0.18, warmth=0.72),
    VoiceProfile("brassquill", "Brass Quill", base_frequency=135, pace=0.88, brightness=0.42, grit=0.38, warmth=0.62),
    VoiceProfile("sparkmint", "Spark Mint", base_frequency=235, pace=1.16, brightness=0.86, grit=0.08, warmth=0.4),
    VoiceProfile("velvetgear", "Velvet Gear", base_frequency=155, pace=0.8, brightness=0.36, grit=0.25, warmth=0.85),
]


DEFAULT_RIGS = [
    PuppetRig("copper-lantern", "Copper Lantern", "#b85f37", "#ffd166", "#f6fff8", "#2b1310", "lantern"),
    PuppetRig("ink-captain", "Ink Captain", "#21304d", "#8ecae6", "#f8f9ff", "#0b1020", "captain"),
    PuppetRig("moss-oracle", "Moss Oracle", "#457b5a", "#f1c453", "#f8ffe5", "#1f1a17", "oracle"),
    PuppetRig("chalk-spark", "Chalk Spark", "#f4f1de", "#e07a5f", "#1f2937", "#111827", "sprite"),
]


DEFAULT_CHARACTERS = [
    Character(
        id="nixie-lumen",
        name="Nixie Lumen",
        role="stage engineer with impossible enthusiasm",
        lore="Nixie builds tiny suns for stage lamps and treats every bug like a dramatic lighting cue.",
        speech_style="quick, vivid, practical, with theatre-craft metaphors and crisp next steps",
        traits=["inventive", "warm", "kinetic", "stagecraft"],
        emotional_range=0.82,
        chaos=0.35,
        kindness=0.78,
        voice=DEFAULT_VOICES[2],
        rig=DEFAULT_RIGS[0],
    ),
    Character(
        id="marlowe-veil",
        name="Marlowe Veil",
        role="melancholy detective narrator",
        lore="Marlowe keeps a notebook full of unsolved feelings and stage directions written in rain.",
        speech_style="dry, observant, noir-leaning, emotionally precise, never melodramatic",
        traits=["noir", "wry", "careful", "memory"],
        emotional_range=0.62,
        chaos=0.18,
        kindness=0.58,
        voice=DEFAULT_VOICES[1],
        rig=DEFAULT_RIGS[1],
    ),
    Character(
        id="oma-sprocket",
        name="Oma Sprocket",
        role="retired clockmaker and gentle systems thinker",
        lore="Oma repairs broken machines by asking them what rhythm they miss.",
        speech_style="patient, tactile, wise, full of small mechanical images and gentle challenge",
        traits=["wise", "mechanical", "grounded", "mentor"],
        emotional_range=0.72,
        chaos=0.12,
        kindness=0.9,
        voice=DEFAULT_VOICES[3],
        rig=DEFAULT_RIGS[2],
    ),
    Character(
        id="pippa-static",
        name="Pippa Static",
        role="signal sprite who turns confusion into games",
        lore="Pippa lives between radio stations and speaks in bright little sparks of pattern.",
        speech_style="playful, concise, clever, occasionally singsong but never childish",
        traits=["playful", "pattern", "electric", "comic"],
        emotional_range=0.9,
        chaos=0.54,
        kindness=0.7,
        voice=DEFAULT_VOICES[0],
        rig=DEFAULT_RIGS[3],
    ),
]


DEFAULT_SCENES = [
    Scene(
        id="workshop-stage",
        name="Workshop Stage",
        setting="A compact theatre workshop where tools, lamps, and puppet strings are part of the scenery.",
        mood="inventive and intimate",
        lighting="amber work lights with cool edge light",
        camera="wide stage view with occasional close-up beats",
    ),
    Scene(
        id="moonlit-control-room",
        name="Moonlit Control Room",
        setting="A quiet broadcast room with reels, monitors, hand-written cue cards, and a glass booth.",
        mood="late-night curious",
        lighting="blue desk glow with warm practical lamps",
        camera="slow two-shot that follows the active speaker",
    ),
]

