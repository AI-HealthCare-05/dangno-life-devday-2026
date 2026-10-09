"""Prepare generated avatar PNGs as web-ready transparent WebP assets."""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from PIL import Image


def remove_edge_connected_light_background(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    if image.mode == "RGBA" and rgba.getextrema()[3][0] < 255:
        return rgba

    pixels = rgba.load()
    width, height = rgba.size
    visited = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def is_light_neutral(x: int, y: int) -> bool:
        red, green, blue, _ = pixels[x, y]
        return min(red, green, blue) >= 218 and max(red, green, blue) - min(red, green, blue) <= 22

    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))

    while queue:
        x, y = queue.popleft()
        index = y * width + x
        if visited[index] or not is_light_neutral(x, y):
            continue
        visited[index] = 1
        red, green, blue, _ = pixels[x, y]
        pixels[x, y] = (red, green, blue, 0)
        for next_x, next_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= next_x < width and 0 <= next_y < height:
                queue.append((next_x, next_y))
    return rgba


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-dir", type=Path, default=Path("src/frontend/assets"))
    args = parser.parse_args()

    sources = sorted(args.asset_dir.glob("lifestyle-avatar-*.png"))
    if not sources:
        raise SystemExit("No lifestyle avatar PNG assets found.")
    for source in sources:
        prepared = remove_edge_connected_light_background(Image.open(source))
        destination = source.with_name(source.stem.replace("-v1", "-20") + ".webp")
        prepared.save(destination, "WEBP", quality=88, method=6, exact=True)
        print(f"prepared {source.name} -> {destination.name}")


if __name__ == "__main__":
    main()
