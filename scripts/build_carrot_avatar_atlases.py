"""Normalize concept-art avatar boards into exact animation atlases.

The original images contain four poses per visual row, but they are not an
equal-width spritesheet. This builder detects each isolated alpha component,
anchors it at the bottom centre of a fixed 224x288 cell, and emits an atlas
that can be sliced without neighbouring-frame bleed.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "src" / "frontend" / "assets"
CELL_WIDTH = 224
CELL_HEIGHT = 288
BOTTOM_PADDING = 10
PRESETS = {
    "red_bow": ("carrot-forest-preset-red-bow-v1.png", [0, 244, 466, 658, 846, 1045, 1254]),
    "cow_hood": ("carrot-forest-preset-cow-hood-v1.png", [0, 260, 502, 740, 968, 1254]),
    "midnight": ("carrot-forest-preset-midnight-v1.png", [0, 207, 410, 605, 796, 1008, 1254]),
    "blue_cap": ("carrot-forest-preset-blue-cap-v1.png", [0, 212, 412, 603, 796, 1013, 1254]),
    "teal_bob": ("carrot-forest-preset-teal-bob-v1.png", [0, 218, 415, 600, 782, 999, 1254]),
}


def occupied_intervals(alpha: Image.Image, gap: int = 3) -> list[tuple[int, int]]:
    """Return horizontal alpha runs, merging tiny outline gaps."""
    bounds = alpha.getbbox()
    if bounds is None:
        return []
    occupied = [x for x in range(alpha.width) if alpha.crop((x, 0, x + 1, alpha.height)).getbbox() is not None]
    intervals: list[tuple[int, int]] = []
    start = previous = occupied[0]
    for x in occupied[1:]:
        if x - previous > gap:
            intervals.append((start, previous + 1))
            start = x
        previous = x
    intervals.append((start, previous + 1))
    return intervals


def normalize_preset(preset: str, source_name: str, row_edges: list[int]) -> dict[str, object]:
    source = Image.open(ASSET_DIR / source_name).convert("RGBA")
    rows = len(row_edges) - 1
    atlas = Image.new("RGBA", (CELL_WIDTH * 4, CELL_HEIGHT * rows), (0, 0, 0, 0))
    frame_manifest: list[dict[str, object]] = []

    for row in range(rows):
        y0, y1 = row_edges[row : row + 2]
        row_image = source.crop((0, y0, source.width, y1))
        intervals = occupied_intervals(row_image.getchannel("A"))
        if len(intervals) != 4:
            raise ValueError(f"{source_name} row {row}: expected 4 sprites, found {intervals}")

        for column, (x0, x1) in enumerate(intervals):
            rough = row_image.crop((x0, 0, x1, row_image.height))
            bbox = rough.getbbox()
            if bbox is None:
                raise ValueError(f"{source_name} row {row} column {column}: empty sprite")
            sprite = rough.crop(bbox)
            if sprite.width > CELL_WIDTH or sprite.height > CELL_HEIGHT - BOTTOM_PADDING:
                raise ValueError(
                    f"{source_name} row {row} column {column}: sprite {sprite.size} exceeds normalized cell"
                )
            paste_x = column * CELL_WIDTH + (CELL_WIDTH - sprite.width) // 2
            paste_y = row * CELL_HEIGHT + CELL_HEIGHT - BOTTOM_PADDING - sprite.height
            atlas.alpha_composite(sprite, (paste_x, paste_y))
            frame_manifest.append(
                {
                    "row": row,
                    "column": column,
                    "source_bbox": [x0 + bbox[0], y0 + bbox[1], x0 + bbox[2], y0 + bbox[3]],
                    "normalized_bbox": [
                        paste_x - column * CELL_WIDTH,
                        paste_y - row * CELL_HEIGHT,
                        paste_x - column * CELL_WIDTH + sprite.width,
                        paste_y - row * CELL_HEIGHT + sprite.height,
                    ],
                }
            )

    output_name = f"carrot-forest-avatar-{preset}-normalized-v2.png"
    atlas.save(ASSET_DIR / output_name, optimize=True)
    return {"file": output_name, "rows": rows, "frames": frame_manifest}


def main() -> None:
    manifest = {
        "version": 2,
        "cell_width": CELL_WIDTH,
        "cell_height": CELL_HEIGHT,
        "columns": 4,
        "direction_rows": {"down": 0, "up": 1, "left": 2, "right": 3},
        "vehicle_rows": {"idle": 4, "moving": 5},
        "presets": {},
    }
    for preset, (source_name, row_edges) in PRESETS.items():
        manifest["presets"][preset] = normalize_preset(preset, source_name, row_edges)
    manifest_path = ASSET_DIR / "carrot-forest-avatar-manifest-v2.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(PRESETS)} normalized atlases and {manifest_path.name}")


if __name__ == "__main__":
    main()
