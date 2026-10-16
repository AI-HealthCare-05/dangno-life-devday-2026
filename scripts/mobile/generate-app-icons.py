"""Resize approved A artwork for native launcher icons (Pillow required).
Run from the repository root: python scripts/mobile/generate-app-icons.py
Only deterministic resizing/padding; no mascot redraw.
"""
from pathlib import Path
import hashlib
import json
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
MASTER = ROOT / "scripts/mobile/assets/hyeoldangi-app-icon-a.png"
RES = ROOT / "src/frontend/native/android/app/src/main/res"
IOS = ROOT / "src/frontend/native/ios/App/App/Assets.xcassets/AppIcon.appiconset"
DENSITIES = {"mdpi": (48, 108), "hdpi": (72, 162), "xhdpi": (96, 216),
             "xxhdpi": (144, 324), "xxxhdpi": (192, 432)}
art = Image.open(MASTER).convert("RGB")
assert art.width == art.height
outputs = []

def write(image, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)
    with Image.open(path) as saved:
        assert saved.size == image.size
        assert saved.mode == "RGB", "Opaque launcher artwork required"
    outputs.append({"path": str(path.relative_to(ROOT)), "size": list(image.size),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})

for density, (legacy, adaptive) in DENSITIES.items():
    folder = RES / ("mipmap-" + density)
    icon = art.resize((legacy, legacy), Image.Resampling.LANCZOS)
    write(icon, folder / "ic_launcher.png")
    write(icon, folder / "ic_launcher_round.png")
    # Android adaptive layers are 108dp; central 72dp is the visible viewport.
    # Fit the entire approved square in 66dp, keeping the droplet safely inside
    # circle/squircle masks and leaving room for launcher parallax.
    side = round(adaptive * 66 / 108)
    foreground = Image.new("RGB", (adaptive, adaptive), art.getpixel((0, 0)))
    foreground.paste(art.resize((side, side), Image.Resampling.LANCZOS),
                     ((adaptive - side) // 2, (adaptive - side) // 2))
    write(foreground, folder / "ic_launcher_foreground.png")

write(art.resize((1024, 1024), Image.Resampling.LANCZOS), IOS / "AppIcon-512@2x.png")
manifest = json.loads((IOS / "Contents.json").read_text(encoding="utf-8"))
assert manifest["images"][0]["filename"] == "AppIcon-512@2x.png"
print(json.dumps({"masterSha256": hashlib.sha256(MASTER.read_bytes()).hexdigest(),
                  "files": outputs}, indent=2))
