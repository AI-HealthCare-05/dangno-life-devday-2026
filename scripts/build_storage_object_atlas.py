"""Normalize the generated 5x4 storage sheet into isolated 256px cells.

The source artwork is not aligned to exact grid boundaries.  Cropping it with
CSS background-position can therefore reveal a few pixels from a neighbour.
This builder finds the connected alpha component nearest each logical cell,
isolates it, and places it inside a padded deterministic atlas cell.
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from PIL import Image

COLUMNS = 5
ROWS = 4
CELL_SIZE = 256
CONTENT_SIZE = 224
ALPHA_THRESHOLD = 12


def connected_components(image: Image.Image) -> list[list[tuple[int, int]]]:
    alpha = image.getchannel("A")
    width, height = image.size
    pixels = alpha.load()
    visited = bytearray(width * height)
    components: list[list[tuple[int, int]]] = []

    for y in range(height):
        for x in range(width):
            index = y * width + x
            if visited[index] or pixels[x, y] <= ALPHA_THRESHOLD:
                continue
            visited[index] = 1
            queue = deque([(x, y)])
            component: list[tuple[int, int]] = []
            while queue:
                current_x, current_y = queue.popleft()
                component.append((current_x, current_y))
                for next_x, next_y in (
                    (current_x - 1, current_y),
                    (current_x + 1, current_y),
                    (current_x, current_y - 1),
                    (current_x, current_y + 1),
                    (current_x - 1, current_y - 1),
                    (current_x + 1, current_y - 1),
                    (current_x - 1, current_y + 1),
                    (current_x + 1, current_y + 1),
                ):
                    if next_x < 0 or next_y < 0 or next_x >= width or next_y >= height:
                        continue
                    next_index = next_y * width + next_x
                    if visited[next_index] or pixels[next_x, next_y] <= ALPHA_THRESHOLD:
                        continue
                    visited[next_index] = 1
                    queue.append((next_x, next_y))
            if len(component) >= 80:
                components.append(component)
    return components


def component_bounds(component: list[tuple[int, int]]) -> tuple[int, int, int, int]:
    xs = [point[0] for point in component]
    ys = [point[1] for point in component]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def build(source: Path, output: Path) -> None:
    with Image.open(source) as raw:
        image = raw.convert("RGBA")
        components = connected_components(image)
        if len(components) < COLUMNS * ROWS:
            raise ValueError(f"expected at least 20 object components, found {len(components)}")

        atlas = Image.new("RGBA", (CELL_SIZE * COLUMNS, CELL_SIZE * ROWS))
        used: set[int] = set()
        cell_width = image.width / COLUMNS
        cell_height = image.height / ROWS

        for row in range(ROWS):
            for column in range(COLUMNS):
                center_x = (column + 0.5) * cell_width
                center_y = (row + 0.5) * cell_height
                candidates: list[tuple[float, int]] = []
                for index, component in enumerate(components):
                    if index in used:
                        continue
                    left, top, right, bottom = component_bounds(component)
                    component_x = (left + right) / 2
                    component_y = (top + bottom) / 2
                    distance = ((component_x - center_x) / cell_width) ** 2 + (
                        (component_y - center_y) / cell_height
                    ) ** 2
                    area_bonus = min(len(component) / 80000, 0.35)
                    candidates.append((distance - area_bonus, index))
                _, selected_index = min(candidates)
                used.add(selected_index)
                component = components[selected_index]
                left, top, right, bottom = component_bounds(component)

                mask = Image.new("L", (right - left, bottom - top))
                mask_pixels = mask.load()
                for point_x, point_y in component:
                    mask_pixels[point_x - left, point_y - top] = image.getpixel((point_x, point_y))[3]
                crop = image.crop((left, top, right, bottom))
                crop.putalpha(mask)
                scale = min(CONTENT_SIZE / crop.width, CONTENT_SIZE / crop.height)
                resized = crop.resize(
                    (max(1, round(crop.width * scale)), max(1, round(crop.height * scale))),
                    Image.Resampling.LANCZOS,
                )
                target_x = column * CELL_SIZE + (CELL_SIZE - resized.width) // 2
                target_y = row * CELL_SIZE + CELL_SIZE - 10 - resized.height
                atlas.alpha_composite(resized, (target_x, target_y))

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
