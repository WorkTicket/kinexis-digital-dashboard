"""Generate Kinexis window + tray + installer icons from the brand logo."""

from pathlib import Path

try:
    from PIL import Image
except ImportError:
    raise SystemExit("Install Pillow first: pip install pillow")

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "electron" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

# Preferred source: committed brand asset
SOURCE_CANDIDATES = [
    ASSETS / "logo-source.png",
    ROOT / "frontend" / "public" / "logo-source.png",
]


def find_source() -> Path:
    for p in SOURCE_CANDIDATES:
        if p.is_file():
            return p
    raise SystemExit("No logo source found. Place logo-source.png in electron/assets/")


def nearly_black(pixel, threshold: int = 28) -> bool:
    r, g, b = pixel[:3]
    a = pixel[3] if len(pixel) > 3 else 255
    if a < 16:
        return True
    return r <= threshold and g <= threshold and b <= threshold


def knock_out_black(img: Image.Image, threshold: int = 28) -> Image.Image:
    """Make near-black background transparent so tray/icons work on any theme."""
    rgba = img.convert("RGBA")
    pixels = rgba.load()
    w, h = rgba.size
    for y in range(h):
        for x in range(w):
            if nearly_black(pixels[x, y], threshold):
                pixels[x, y] = (0, 0, 0, 0)
    return rgba


def content_bbox(img: Image.Image, alpha_min: int = 20):
    rgba = img.convert("RGBA")
    pixels = rgba.load()
    w, h = rgba.size
    min_x, min_y, max_x, max_y = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if pixels[x, y][3] >= alpha_min:
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y
    if max_x < 0:
        return (0, 0, w, h)
    return (min_x, min_y, max_x + 1, max_y + 1)


def to_square_icon(src: Image.Image, size: int, padding_ratio: float = 0.12) -> Image.Image:
    """Crop to logo content, pad to square, scale to size."""
    cropped = src.crop(content_bbox(src))
    cw, ch = cropped.size
    side = max(cw, ch)
    pad = int(side * padding_ratio)
    canvas_side = side + pad * 2
    canvas = Image.new("RGBA", (canvas_side, canvas_side), (0, 0, 0, 0))
    ox = (canvas_side - cw) // 2
    oy = (canvas_side - ch) // 2
    canvas.paste(cropped, (ox, oy), cropped)
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def main():
    source_path = find_source()
    print(f"Using logo source: {source_path}")

    # Persist a canonical copy in assets for future builds
    raw = Image.open(source_path).convert("RGBA")
    canonical = ASSETS / "logo-source.png"
    if source_path.resolve() != canonical.resolve():
        raw.save(canonical)

    transparent = knock_out_black(raw)

    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [to_square_icon(transparent, s) for s in sizes]
    master = images[-1]  # 256

    # Multi-resolution Windows icon (desktop shortcut + taskbar + exe)
    # Pillow saves multi-resolution ICO with append_images for all sizes
    master.save(
        ASSETS / "icon.ico",
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=[to_square_icon(transparent, s) for s in sizes if s != 256],
    )
    master.save(ASSETS / "icon.png")
    images[2].save(ASSETS / "tray-icon.png")  # 32px tray
    images[1].save(ASSETS / "tray-icon-24.png")

    # In-app / web assets
    public = ROOT / "frontend" / "public"
    public.mkdir(parents=True, exist_ok=True)
    master.save(public / "logo.png")
    master.save(public / "icon-256.png")
    images[5].save(public / "logo-mark.png")  # 128

    print(f"Wrote icons to {ASSETS}")
    print(f"Wrote UI logos to {public}")


if __name__ == "__main__":
    main()
