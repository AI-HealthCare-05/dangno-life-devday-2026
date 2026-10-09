"""Generate the original sound-effect pack used by Carrot Forest.

The effects are synthesized from simple oscillators and seeded noise, so the
project can ship them without relying on third-party game audio.
"""

from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path

RATE = 44_100
OUTPUT = Path(__file__).resolve().parents[1] / "src" / "frontend" / "assets" / "sfx"


def envelope(index: int, length: int, attack: float = 0.04, release: float = 0.3) -> float:
    position = index / max(1, length - 1)
    fade_in = min(1.0, position / max(attack, 0.001))
    fade_out = min(1.0, (1.0 - position) / max(release, 0.001))
    return min(fade_in, fade_out)


def tone(
    duration: float,
    start_hz: float,
    end_hz: float | None = None,
    *,
    volume: float = 0.35,
    wave_kind: str = "sine",
    attack: float = 0.02,
    release: float = 0.3,
) -> list[float]:
    total = max(1, round(duration * RATE))
    end_hz = start_hz if end_hz is None else end_hz
    phase = 0.0
    samples: list[float] = []
    for index in range(total):
        progress = index / max(1, total - 1)
        frequency = start_hz + (end_hz - start_hz) * progress
        phase += 2 * math.pi * frequency / RATE
        if wave_kind == "triangle":
            raw = 2 / math.pi * math.asin(math.sin(phase))
        elif wave_kind == "square":
            raw = 1.0 if math.sin(phase) >= 0 else -1.0
        else:
            raw = math.sin(phase)
        samples.append(raw * envelope(index, total, attack, release) * volume)
    return samples


def noise(duration: float, *, volume: float = 0.2, release: float = 0.35, seed: int = 1) -> list[float]:
    rng = random.Random(seed)
    total = max(1, round(duration * RATE))
    previous = 0.0
    samples: list[float] = []
    for index in range(total):
        # Smoothed noise avoids a harsh static-like result.
        previous = previous * 0.62 + rng.uniform(-1.0, 1.0) * 0.38
        samples.append(previous * envelope(index, total, 0.01, release) * volume)
    return samples


def mix(*tracks: tuple[list[float], float]) -> list[float]:
    length = max((round(delay * RATE) + len(samples) for samples, delay in tracks), default=0)
    result = [0.0] * length
    for samples, delay in tracks:
        offset = round(delay * RATE)
        for index, sample in enumerate(samples):
            result[offset + index] += sample
    peak = max((abs(value) for value in result), default=1.0)
    if peak > 0.92:
        result = [value * 0.92 / peak for value in result]
    return result


def write(name: str, samples: list[float]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUTPUT / name), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(RATE)
        target.writeframes(b"".join(struct.pack("<h", round(max(-1, min(1, value)) * 32767)) for value in samples))


def chord(notes: tuple[float, ...], duration: float, *, volume: float = 0.22) -> list[float]:
    return mix(*((tone(duration, note, volume=volume, release=0.42), 0.0) for note in notes))


def main() -> None:
    effects = {
        "step-grass.wav": mix(
            (noise(0.075, volume=0.17, release=0.75, seed=11), 0), (tone(0.07, 105, 72, volume=0.12), 0)
        ),
        "run-grass.wav": mix(
            (noise(0.06, volume=0.2, release=0.7, seed=13), 0), (tone(0.055, 145, 88, volume=0.13), 0)
        ),
        "door-open.wav": mix(
            (tone(0.22, 176, 116, volume=0.2, wave_kind="triangle"), 0),
            (noise(0.3, volume=0.09, release=0.65, seed=17), 0.06),
            (tone(0.11, 720, 520, volume=0.13), 0.22),
        ),
        "sit-cloth.wav": mix(
            (noise(0.14, volume=0.12, release=0.7, seed=19), 0), (tone(0.12, 120, 82, volume=0.11), 0.03)
        ),
        "mount.wav": mix((tone(0.12, 330, 520, volume=0.18), 0), (tone(0.16, 520, 760, volume=0.14), 0.08)),
        "harvest.wav": mix(
            (noise(0.18, volume=0.16, release=0.5, seed=23), 0),
            (tone(0.18, 210, 390, volume=0.18, wave_kind="triangle"), 0.05),
            (tone(0.16, 520, 740, volume=0.13), 0.16),
        ),
        "water.wav": mix(
            (noise(0.65, volume=0.13, release=0.35, seed=29), 0), (tone(0.5, 920, 610, volume=0.06), 0.04)
        ),
        "fishing-cast.wav": mix(
            (noise(0.38, volume=0.13, release=0.7, seed=31), 0), (tone(0.36, 980, 240, volume=0.12), 0)
        ),
        "fishing-catch.wav": mix(
            (tone(0.15, 440, 660, volume=0.21), 0),
            (tone(0.18, 660, 880, volume=0.18), 0.12),
            (noise(0.13, volume=0.1, release=0.5, seed=37), 0.04),
        ),
        "attack-sword.wav": mix(
            (noise(0.24, volume=0.17, release=0.75, seed=41), 0),
            (tone(0.24, 1450, 180, volume=0.2, wave_kind="triangle"), 0),
        ),
        "attack-bow.wav": mix(
            (tone(0.13, 230, 720, volume=0.2, wave_kind="triangle"), 0),
            (noise(0.2, volume=0.11, release=0.8, seed=43), 0.08),
        ),
        "attack-magic.wav": mix(
            (tone(0.42, 480, 980, volume=0.16), 0),
            (tone(0.36, 720, 1440, volume=0.12), 0.05),
            (chord((523.25, 659.25, 783.99), 0.28, volume=0.08), 0.22),
        ),
        "rat-caught.wav": mix(
            (tone(0.11, 420, 210, volume=0.18, wave_kind="triangle"), 0),
            (chord((523.25, 659.25, 783.99), 0.32, volume=0.13), 0.1),
        ),
        "pet-feed.wav": mix(
            (tone(0.15, 660, 880, volume=0.16), 0),
            (tone(0.18, 880, 1046.5, volume=0.14), 0.12),
            (tone(0.22, 1046.5, 1318.5, volume=0.12), 0.25),
        ),
        "dance.wav": mix(
            (tone(0.11, 523.25, volume=0.14), 0),
            (tone(0.11, 659.25, volume=0.14), 0.14),
            (tone(0.16, 783.99, volume=0.14), 0.28),
        ),
        "place-object.wav": mix((tone(0.1, 240, 180, volume=0.18), 0), (tone(0.15, 440, 660, volume=0.12), 0.1)),
        "object-on.wav": mix(
            (tone(0.12, 360, 620, volume=0.17), 0),
            (tone(0.2, 620, 880, volume=0.13), 0.09),
        ),
        "object-off.wav": mix(
            (tone(0.16, 520, 260, volume=0.16, wave_kind="triangle"), 0),
            (tone(0.1, 220, 150, volume=0.1), 0.11),
        ),
        "cow-toggle.wav": mix(
            (tone(0.18, 190, 145, volume=0.17, wave_kind="triangle"), 0),
            (tone(0.22, 155, 118, volume=0.15, wave_kind="triangle"), 0.14),
            (tone(0.12, 520, 680, volume=0.08), 0.3),
        ),
    }
    for name, samples in effects.items():
        write(name, samples)
    print(f"generated {len(effects)} original effects in {OUTPUT}")


if __name__ == "__main__":
    main()
