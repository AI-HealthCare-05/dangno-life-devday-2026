"""Build the extinguished campfire from the exact ON-state atlas cell."""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/frontend/assets/carrot-forest-storage-atlas-v3.png"
OUTPUT = ROOT / "src/frontend/assets/carrot-forest-campfire-off-v3.png"


def main() -> None:  # noqa: C901 - deterministic pixel-mask stages are clearer inline
    atlas = Image.open(SOURCE).convert("RGBA")
    campfire = atlas.crop((1024, 512, 1280, 768))
    pixels = campfire.load()
    for y in range(22, 158):
        for x in range(72, 186):
            red, green, blue, alpha = pixels[x, y]
            if not alpha:
                continue
            in_flame_shape = (y < 126 and abs(x - 130) < min(48, 9 + (y - 22) * 0.47)) or (
                y >= 126 and abs(x - 130) < 34
            )
            flame_silhouette = in_flame_shape and ((red - green > 20 and red - blue > 30) or max(red, green, blue) < 72)
            upper_flame = y < 126 and 78 < x < 182 and red > 74 and red - green > 16 and red - blue > 24 and blue < 130
            lower_flame = y >= 121 and red > 226 and (green > 122 or red - green > 118) and blue < 105
            if flame_silhouette or upper_flame or lower_flame:
                pixels[x, y] = (0, 0, 0, 0)

    ash = Image.new("RGBA", campfire.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(ash)
    draw.ellipse((94, 112, 166, 164), fill=(67, 64, 61, 255))
    draw.ellipse((101, 117, 158, 157), fill=(112, 107, 100, 255))
    draw.ellipse((111, 124, 149, 151), fill=(151, 144, 133, 245))
    for box, color in [
        ((106, 139, 114, 146), (40, 39, 38, 255)),
        ((139, 132, 148, 140), (47, 45, 43, 255)),
        ((130, 147, 138, 154), (53, 50, 47, 255)),
        ((121, 128, 126, 134), (132, 48, 29, 225)),
        ((143, 143, 147, 147), (116, 39, 26, 205)),
    ]:
        draw.ellipse(box, fill=color)
    result = Image.alpha_composite(campfire, ash)
    result_pixels = result.load()
    for y in range(38, 161):
        for x in range(80, 181):
            red, green, blue, alpha = result_pixels[x, y]
            if y < 112 and abs(x - 130) < min(51, 10 + (y - 22) * 0.48):
                result_pixels[x, y] = (0, 0, 0, 0)
                continue
            warm = alpha and red > 66 and red - green > 15 and red - blue > 22
            if not warm:
                continue
            if y < 112:
                result_pixels[x, y] = (0, 0, 0, 0)
            elif 90 < x < 170:
                charcoal = max(42, min(92, round((red + green + blue) / 4.3)))
                result_pixels[x, y] = (charcoal, charcoal - 3, charcoal - 5, alpha)
    result.save(OUTPUT, optimize=True)


if __name__ == "__main__":
    main()
