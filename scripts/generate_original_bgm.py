"""Generate the original looping BGM used by Carrot Forest.

The score and synthesis are intentionally self-contained so the two release
tracks can be reproduced without carrying third-party music into the build.
"""

from __future__ import annotations

import math
import random
import wave
from array import array
from pathlib import Path

SAMPLE_RATE = 32_000
ASSET_DIR = Path(__file__).resolve().parents[1] / "src" / "frontend" / "assets"


def midi_hz(note: int) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def oscillator(kind: str, phase: float) -> float:
    sine = math.sin(phase)
    if kind == "triangle":
        return 2.0 / math.pi * math.asin(sine)
    if kind == "wood":
        return 0.72 * sine + 0.20 * math.sin(2 * phase) + 0.08 * math.sin(3 * phase)
    if kind == "bell":
        return 0.68 * sine + 0.22 * math.sin(2.01 * phase) + 0.10 * math.sin(3.97 * phase)
    return sine


def add_note(
    track: list[float],
    start: float,
    duration: float,
    note: int,
    volume: float,
    *,
    kind: str = "sine",
    attack: float = 0.015,
    release: float = 0.12,
    decay: float = 0.0,
) -> None:
    first = max(0, int(start * SAMPLE_RATE))
    last = min(len(track), int((start + duration) * SAMPLE_RATE))
    frequency = midi_hz(note)
    for index in range(first, last):
        elapsed = index / SAMPLE_RATE - start
        remaining = start + duration - index / SAMPLE_RATE
        envelope = min(1.0, elapsed / max(attack, 1e-4), remaining / max(release, 1e-4))
        if decay:
            envelope *= math.exp(-decay * elapsed)
        track[index] += volume * envelope * oscillator(kind, 2 * math.pi * frequency * elapsed)


def add_shaker(track: list[float], start: float, volume: float, rng: random.Random) -> None:
    first = int(start * SAMPLE_RATE)
    length = int(0.055 * SAMPLE_RATE)
    previous = 0.0
    for offset in range(length):
        index = first + offset
        if index >= len(track):
            break
        noise = rng.uniform(-1.0, 1.0)
        bright = noise - 0.72 * previous
        previous = noise
        envelope = math.exp(-42 * offset / SAMPLE_RATE)
        track[index] += bright * envelope * volume


def add_chord(track: list[float], start: float, duration: float, notes: tuple[int, ...], volume: float) -> None:
    for note in notes:
        add_note(track, start, duration, note, volume / len(notes), kind="wood", attack=0.18, release=0.3)


def normalize_and_write(track: list[float], path: Path) -> None:
    edge = int(0.06 * SAMPLE_RATE)
    for index in range(edge):
        fade = index / edge
        track[index] *= fade
        track[-index - 1] *= fade
    peak = max(max(abs(value) for value in track), 1e-8)
    scale = 0.86 / peak
    pcm = array("h", (round(max(-1.0, min(1.0, value * scale)) * 32767) for value in track))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm.tobytes())


def build_garden() -> list[float]:
    bpm = 96
    beat = 60 / bpm
    bars = 16
    track = [0.0] * int(bars * 4 * beat * SAMPLE_RATE)
    rng = random.Random(20260901)
    chords = (
        (60, 64, 67, 71),
        (57, 60, 64, 67),
        (53, 57, 60, 64),
        (55, 60, 62, 67),
        (52, 55, 59, 64),
        (57, 60, 64, 69),
        (50, 53, 57, 62),
        (55, 59, 62, 67),
    )
    bass = (36, 33, 29, 31, 28, 33, 26, 31)
    motif = (
        (0.0, 67, 0.5),
        (0.75, 69, 0.25),
        (1.0, 71, 0.5),
        (1.75, 72, 0.25),
        (2.0, 76, 0.5),
        (2.75, 72, 0.25),
        (3.0, 71, 0.5),
        (3.5, 69, 0.5),
    )
    answer = (
        (0.0, 64, 0.5),
        (0.5, 67, 0.5),
        (1.25, 69, 0.5),
        (2.0, 72, 0.5),
        (2.75, 71, 0.25),
        (3.0, 69, 0.5),
        (3.5, 67, 0.5),
    )
    for bar in range(bars):
        start = bar * 4 * beat
        add_chord(track, start, 4 * beat, chords[bar % len(chords)], 0.30)
        for pulse in range(4):
            add_note(track, start + pulse * beat, 0.72 * beat, bass[bar % len(bass)], 0.13, kind="triangle")
        phrase = motif if bar % 4 in (0, 1) else answer
        transpose = 0 if bar < 8 else 12
        for offset, note, length in phrase:
            add_note(
                track,
                start + offset * beat,
                length * beat,
                note + transpose,
                0.18,
                kind="bell",
                release=0.16,
                decay=1.8,
            )
        for eighth in range(8):
            add_shaker(track, start + eighth * beat / 2, 0.018 if eighth % 2 == 0 else 0.012, rng)
    return track


def build_home_canopy() -> list[float]:  # noqa: C901
    """Build a bright 96-second canopy loop for the house scene."""
    bpm = 80
    beat = 60 / bpm
    bars = 32
    track = [0.0] * int(bars * 4 * beat * SAMPLE_RATE)
    rng = random.Random(20260903)
    chords = (
        (48, 52, 55, 59, 62),
        (52, 55, 59, 62),
        (45, 48, 52, 55),
        (41, 45, 48, 52),
        (50, 53, 57, 60),
        (43, 48, 50, 55),
        (41, 45, 48, 52),
        (43, 47, 50, 55),
    )
    bass = (36, 40, 33, 29, 38, 31, 29, 31)
    main_motif = (
        (0.0, 67, 0.5),
        (0.75, 71, 0.25),
        (1.0, 74, 0.5),
        (1.75, 76, 0.25),
        (2.0, 74, 0.5),
        (3.0, 71, 0.5),
    )
    high_answer = (
        (0.5, 79, 0.35),
        (1.25, 81, 0.35),
        (2.0, 83, 0.35),
        (2.75, 81, 0.35),
        (3.25, 79, 0.5),
    )
    for bar in range(bars):
        start = bar * 4 * beat
        chord = chords[bar % len(chords)]
        section = bar // 8
        pad_volume = (0.17, 0.20, 0.23, 0.25)[section]
        add_chord(track, start, 4 * beat, chord, pad_volume)

        # The opening stays sparse; bass and arpeggios enter in the middle.
        if section >= 1:
            for pulse in range(4):
                add_note(
                    track,
                    start + pulse * beat,
                    0.75 * beat,
                    bass[bar % len(bass)],
                    0.072 if section == 1 else 0.095,
                    kind="triangle",
                    attack=0.08,
                    release=0.2,
                )
            for eighth in range(8):
                note = chord[eighth % len(chord)] + 12
                add_note(
                    track,
                    start + eighth * beat / 2,
                    0.32 * beat,
                    note,
                    0.052 if section == 1 else 0.075,
                    kind="wood",
                    release=0.12,
                    decay=1.1,
                )

        # A simple original bell phrase appears every other bar.
        if bar % 2 == 0:
            for offset, note, length in main_motif:
                add_note(
                    track,
                    start + offset * beat,
                    length * beat,
                    note,
                    0.13 if section == 0 else 0.16,
                    kind="bell",
                    attack=0.025,
                    release=0.28,
                    decay=1.15,
                )

        # The latter half adds a high response and a light, breezy pulse.
        if section >= 2:
            for offset, note, length in high_answer:
                add_note(
                    track,
                    start + offset * beat,
                    length * beat,
                    note,
                    0.070 if section == 2 else 0.090,
                    kind="bell",
                    attack=0.02,
                    release=0.2,
                    decay=1.5,
                )
            for eighth in range(8):
                add_shaker(track, start + eighth * beat / 2, 0.009 if eighth % 2 else 0.015, rng)

        # The final eight bars add short upper-register sparkles without becoming heavy.
        if section == 3:
            for pulse in range(4):
                add_note(
                    track,
                    start + (pulse + 0.5) * beat,
                    0.22 * beat,
                    chord[(pulse + 2) % len(chord)] + 24,
                    0.045,
                    kind="bell",
                    attack=0.01,
                    release=0.12,
                    decay=2.4,
                )
    return track


def build_fresh_main() -> list[float]:
    """Build a warm, wistful 111-second woodland-restaurant waltz."""
    bpm = 78
    beat = 60 / bpm
    bars = 48
    beats_per_bar = 3
    track = [0.0] * int(bars * beats_per_bar * beat * SAMPLE_RATE)
    rng = random.Random(20260904)
    chords = (
        (48, 52, 55, 59),
        (45, 48, 52, 55),
        (50, 53, 57, 60),
        (43, 47, 50, 53),
        (52, 55, 59, 64),
        (45, 48, 52, 57),
        (53, 57, 60, 64),
        (43, 47, 50, 53),
    )
    bass = (36, 33, 38, 31, 40, 33, 41, 31)
    motif_a = (
        (0.0, 64, 0.60),
        (1.0, 67, 0.48),
        (2.0, 69, 0.62),
    )
    motif_b = (
        (0.0, 67, 0.50),
        (0.75, 65, 0.30),
        (1.25, 64, 0.55),
        (2.25, 62, 0.48),
    )
    for bar in range(bars):
        start = bar * beats_per_bar * beat
        section = bar // 12
        chord = chords[bar % len(chords)]
        add_chord(track, start, beats_per_bar * beat, chord, (0.12, 0.145, 0.17, 0.19)[section])
        phrase = motif_a if bar % 4 in (0, 1) else motif_b
        for offset, note, length in phrase:
            add_note(
                track,
                start + offset * beat,
                length * beat,
                note,
                0.080 + 0.009 * section,
                kind="wood",
                attack=0.045,
                release=0.30,
                decay=0.75,
            )

        # Waltz pulse: a warm bass note followed by two light wooden chords.
        add_note(
            track,
            start,
            0.62 * beat,
            bass[bar % len(bass)],
            0.065 + 0.008 * section,
            kind="triangle",
            release=0.16,
        )
        if section >= 1:
            for pulse in (1, 2):
                for chord_note in chord:
                    add_note(
                        track,
                        start + pulse * beat,
                        0.38 * beat,
                        chord_note + 12,
                        0.014 + 0.004 * section,
                        kind="wood",
                        release=0.10,
                        decay=1.8,
                    )
        if section >= 2 and bar % 2 == 1:
            for eighth in (1, 3, 5):
                add_note(
                    track,
                    start + eighth * beat / 2,
                    0.18 * beat,
                    chord[(eighth + bar) % len(chord)] + 24,
                    0.018 + 0.005 * section,
                    kind="bell",
                    release=0.09,
                    decay=2.2,
                )
        if section == 3:
            for pulse in range(6):
                add_shaker(track, start + pulse * beat / 2, 0.0035 if pulse % 2 else 0.006, rng)
    return track


def build_avatar() -> list[float]:
    bpm = 120
    beat = 60 / bpm
    bars = 16
    track = [0.0] * int(bars * 4 * beat * SAMPLE_RATE)
    rng = random.Random(20260902)
    chords = (
        (53, 57, 60, 64),
        (55, 59, 62, 67),
        (52, 55, 59, 64),
        (57, 60, 64, 69),
    )
    bass = (41, 43, 40, 45)
    melody = (
        (0.0, 72, 0.25),
        (0.5, 76, 0.25),
        (1.0, 79, 0.5),
        (1.75, 76, 0.25),
        (2.0, 74, 0.25),
        (2.5, 77, 0.25),
        (3.0, 81, 0.5),
        (3.75, 79, 0.25),
    )
    for bar in range(bars):
        start = bar * 4 * beat
        chord = chords[bar % 4]
        for pulse in range(8):
            chord_note = chord[pulse % len(chord)] + (12 if pulse % 2 else 0)
            add_note(
                track, start + pulse * beat / 2, 0.32 * beat, chord_note, 0.10, kind="wood", release=0.06, decay=2.2
            )
        for pulse in range(4):
            add_note(track, start + pulse * beat, 0.55 * beat, bass[bar % 4], 0.12, kind="triangle", release=0.08)
        for offset, note, length in melody:
            variation = 2 if bar % 4 == 3 and offset >= 2 else 0
            add_note(
                track,
                start + offset * beat,
                length * beat,
                note + variation,
                0.18,
                kind="bell",
                release=0.08,
                decay=2.6,
            )
        for eighth in range(8):
            add_shaker(track, start + eighth * beat / 2, 0.022 if eighth in (2, 6) else 0.010, rng)
    return track


def main() -> None:
    normalize_and_write(build_garden(), ASSET_DIR / "carrot-forest-original.wav")
    normalize_and_write(build_home_canopy(), ASSET_DIR / "forest-canopy-original.wav")
    normalize_and_write(build_fresh_main(), ASSET_DIR / "forest-main-breeze-original.wav")
    normalize_and_write(build_avatar(), ASSET_DIR / "avatar-studio-original.wav")


if __name__ == "__main__":
    main()
