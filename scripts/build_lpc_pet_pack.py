"""Build the three-pet Carrot Forest atlas from the credited LPC animal sheet."""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/frontend/assets/lpc-rat-cat-dog-source.png"
OUTPUT = ROOT / "src/frontend/assets/carrot-forest-lpc-pets-v1.png"
RAT_OUTPUT = ROOT / "src/frontend/assets/carrot-forest-lpc-rat-v1.png"
FRAME = 32


def orange_cat(frame: Image.Image) -> Image.Image:
    result = frame.convert("RGBA")
    pixels = result.load()
    for y in range(result.height):
        for x in range(result.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha and max(red, green, blue) < 95:
                brightness = max(red, green, blue) / 95
                pixels[x, y] = (
                    int(112 + 100 * brightness),
                    int(55 + 55 * brightness),
                    int(22 + 24 * brightness),
                    alpha,
                )
    return result


def build() -> None:
    source = Image.open(SOURCE).convert("RGBA")
    atlas = Image.new("RGBA", (9 * FRAME, 4 * FRAME), (0, 0, 0, 0))
    rat_atlas = Image.new("RGBA", (3 * FRAME, 4 * FRAME), (0, 0, 0, 0))
    # Output columns: white cat 0..2, orange cat 3..5, dog 6..8.
    for direction in range(4):
        for animation in range(3):
            white = source.crop(
                ((3 + animation) * FRAME, direction * FRAME, (4 + animation) * FRAME, (direction + 1) * FRAME)
            )
            black = source.crop(
                ((6 + animation) * FRAME, direction * FRAME, (7 + animation) * FRAME, (direction + 1) * FRAME)
            )
            dog = source.crop(
                (animation * FRAME, (4 + direction) * FRAME, (animation + 1) * FRAME, (5 + direction) * FRAME)
            )
            rat = source.crop((animation * FRAME, direction * FRAME, (animation + 1) * FRAME, (direction + 1) * FRAME))
            atlas.alpha_composite(white, (animation * FRAME, direction * FRAME))
            atlas.alpha_composite(orange_cat(black), ((3 + animation) * FRAME, direction * FRAME))
            atlas.alpha_composite(dog, ((6 + animation) * FRAME, direction * FRAME))
            rat_atlas.alpha_composite(rat, (animation * FRAME, direction * FRAME))
    atlas.save(OUTPUT, optimize=True)
    rat_atlas.save(RAT_OUTPUT, optimize=True)


if __name__ == "__main__":
    build()
