from __future__ import annotations

import math
import wave
from pathlib import Path


SampleBuffer = list[float]


def clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def normalize(samples: SampleBuffer, target: float = 0.92) -> SampleBuffer:
    peak = max((abs(s) for s in samples), default=0.0)
    if peak <= 1e-9:
        return samples[:]
    gain = target / peak
    return [clamp(s * gain) for s in samples]


def rms(samples: SampleBuffer) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def pgf_process(samples: SampleBuffer, gamma: float = 0.08, k_value: float = 0.16, steps: int = 4) -> SampleBuffer:
    """Pure-Python 1D Perona-Malik style diffusion for voice cleanup.

    This is inspired by the Psiren PGF direction, written as compact standard
    library code for a dependency-free v1.
    """
    if len(samples) < 4:
        return samples[:]
    current = samples[:]
    k_sq = max(1e-6, k_value * k_value)
    dt = 0.2
    for _ in range(max(1, int(steps))):
        nxt = current[:]
        for i in range(1, len(current) - 1):
            grad_left = current[i] - current[i - 1]
            grad_right = current[i + 1] - current[i]
            conduct_left = math.exp(-(grad_left * grad_left) / k_sq)
            conduct_right = math.exp(-(grad_right * grad_right) / k_sq)
            diffusion = conduct_right * grad_right - conduct_left * grad_left
            nxt[i] = clamp(current[i] + gamma * dt * diffusion)
        current = nxt
    return current


def declick(samples: SampleBuffer, threshold: float = 0.62) -> SampleBuffer:
    if len(samples) < 3:
        return samples[:]
    out = samples[:]
    for i in range(1, len(samples) - 1):
        local = (samples[i - 1] + samples[i + 1]) * 0.5
        if abs(samples[i] - local) > threshold:
            out[i] = local
    return out


def warmth(samples: SampleBuffer, drive: float = 0.26) -> SampleBuffer:
    gain = 1.0 + drive * 1.8
    return [math.tanh(s * gain) / math.tanh(gain) for s in samples]


def clarity(samples: SampleBuffer, amount: float = 0.2) -> SampleBuffer:
    if len(samples) < 3:
        return samples[:]
    out = samples[:]
    for i in range(1, len(samples) - 1):
        blurred = (samples[i - 1] + samples[i] + samples[i + 1]) / 3.0
        out[i] = clamp(samples[i] + (samples[i] - blurred) * amount)
    return out


def master_voice(samples: SampleBuffer, warmth_amount: float = 0.35, cleanup: bool = True) -> SampleBuffer:
    out = samples[:]
    if cleanup:
        out = declick(out)
        out = pgf_process(out, gamma=0.08, k_value=0.16, steps=3)
    out = warmth(out, drive=warmth_amount)
    out = clarity(out, amount=0.18)
    return normalize(out)


def write_wav(path: str | Path, samples: SampleBuffer, sample_rate: int = 22050) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = normalize(samples)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        data = bytearray()
        for sample in samples:
            data.extend(int(clamp(sample) * 32767).to_bytes(2, "little", signed=True))
        wf.writeframes(bytes(data))


def read_wav_mono(path: str | Path) -> tuple[SampleBuffer, int]:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())
    samples: SampleBuffer = []
    step = 2 * channels
    for idx in range(0, len(frames), step):
        channel = int.from_bytes(frames[idx : idx + 2], "little", signed=True)
        samples.append(channel / 32767.0)
    return samples, sample_rate


def duration_seconds(samples: SampleBuffer, sample_rate: int) -> float:
    return len(samples) / float(sample_rate or 1)

