"""Build the production modular avatar atlas from the generated master sheet.

The source sheet is a 4 x 11 visual board.  This script removes the baked
checkerboard with an edge-connected flood fill and normalizes every cell to
the exact runtime contract.  Keeping this step in source control makes the
binary asset reproducible and prevents neighbouring-cell bleed.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "src" / "frontend" / "assets"
SOURCE = ASSET_DIR / "carrot-forest-modular-avatar-master-v3.png"
OUTPUT = ASSET_DIR / "carrot-forest-modular-avatar-atlas-v3.png"

COLUMNS = 4
ROWS = 11
CELL_WIDTH = 224
CELL_HEIGHT = 288
SCALE = 1.12
ROW_BOTTOMS = [260, 209, 196, 188, 187, 194, 260, 260, 260, 260, 260]


def is_background(pixel: tuple[int, int, int]) -> bool:
    low, high = min(pixel), max(pixel)
    return low >= 232 and high - low <= 7


def remove_connected_background(source: Image.Image) -> Image.Image:  # noqa: C901
    """Remove only pale neutral pixels connected to an outer canvas edge.

    The explicit four-neighbour traversal is intentionally kept in one place
    so white pixels enclosed by the avatar outline are never made transparent.
    """
    rgb = source.convert("RGB")
    width, height = rgb.size
    seen = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def enqueue(x: int, y: int) -> None:
        index = y * width + x
        if not seen[index] and is_background(rgb.getpixel((x, y))):
            seen[index] = 1
            queue.append((x, y))

    for x in range(width):
        enqueue(x, 0)
        enqueue(x, height - 1)
    for y in range(height):
        enqueue(0, y)
        enqueue(width - 1, y)

    while queue:
        x, y = queue.popleft()
        if x:
            enqueue(x - 1, y)
        if x + 1 < width:
            enqueue(x + 1, y)
        if y:
            enqueue(x, y - 1)
        if y + 1 < height:
            enqueue(x, y + 1)

    rgba = rgb.convert("RGBA")
    alpha = Image.new("L", (width, height), 255)
    alpha_data = alpha.load()
    for y in range(height):
        offset = y * width
        for x in range(width):
            if seen[offset + x]:
                alpha_data[x, y] = 0
    rgba.putalpha(alpha)
    return rgba


def occupied_intervals(alpha: Image.Image, axis: str, gap: int = 3) -> list[tuple[int, int]]:
    limit = alpha.height if axis == "y" else alpha.width
    occupied: list[int] = []
    for position in range(limit):
        strip = (
            alpha.crop((0, position, alpha.width, position + 1))
            if axis == "y"
            else alpha.crop((position, 0, position + 1, alpha.height))
        )
        if strip.getbbox() is not None:
            occupied.append(position)
    intervals: list[tuple[int, int]] = []
    start = previous = occupied[0]
    for position in occupied[1:]:
        if position - previous > gap:
            intervals.append((start, previous + 1))
            start = position
        previous = position
    intervals.append((start, previous + 1))
    return intervals


def build() -> None:
    source = remove_connected_background(Image.open(SOURCE))
    atlas = Image.new("RGBA", (CELL_WIDTH * COLUMNS, CELL_HEIGHT * ROWS), (0, 0, 0, 0))
    row_intervals = occupied_intervals(source.getchannel("A"), "y")
    if len(row_intervals) != ROWS:
        raise ValueError(f"expected {ROWS} visual rows, found {row_intervals}")

    for row, (top, bottom) in enumerate(row_intervals):
        row_image = source.crop((0, top, source.width, bottom))
        column_intervals = occupied_intervals(row_image.getchannel("A"), "x", gap=8)
        if len(column_intervals) != COLUMNS:
            raise ValueError(f"row {row}: expected {COLUMNS} sprites, found {column_intervals}")
        for column, (left, right) in enumerate(column_intervals):
            sprite = row_image.crop((left, 0, right, row_image.height))
            bbox = sprite.getbbox()
            if bbox is None:
                raise ValueError(f"row {row} column {column}: empty sprite")
            sprite = sprite.crop(bbox)
            resized = sprite.resize(
                (round(sprite.width * SCALE), round(sprite.height * SCALE)),
                Image.Resampling.NEAREST,
            )
            paste_x = column * CELL_WIDTH + (CELL_WIDTH - resized.width) // 2
            paste_y = row * CELL_HEIGHT + ROW_BOTTOMS[row] - resized.height
            atlas.alpha_composite(resized, (paste_x, paste_y))

    atlas.save(OUTPUT, optimize=True)
    print(f"wrote {OUTPUT.name}: {atlas.size}")


if __name__ == "__main__":
    build()
