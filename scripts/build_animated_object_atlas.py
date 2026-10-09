"""Normalize a 4x4 generated animated-object sheet into deterministic 128px cells."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def build(source: Path, output: Path) -> None:
    with Image.open(source) as raw:
        image = raw.convert("RGBA")
        if image.width != image.height:
            raise ValueError("source must be a square 4x4 spritesheet")
        atlas = image.resize((512, 512), Image.Resampling.LANCZOS)
        output.parent.mkdir(parents=True, exist_ok=True)
        atlas.save(output, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build(args.source, args.output)


if __name__ == "__main__":
    main()
