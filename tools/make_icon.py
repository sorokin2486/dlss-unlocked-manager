"""Draw the app icon: a pixel lightning bolt that sharpens from coarse pixels into a smooth shape.

Coarse pixels in the bottom-left resolve into a crisp vector bolt in the top-right, which is
what upscaling does. Writes dlss_manager/ui/assets/icon.png (window icon) and icon.ico (exe icon).

Run:  python tools/make_icon.py   (needs Pillow)
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ASSETS = Path(__file__).resolve().parent.parent / "dlss_manager" / "ui" / "assets"
ICO_SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)]

S = 1024  # drawing canvas; downscaled at the end for anti-aliasing
INSET = int(S * 0.04)
TILE_RADIUS = int(S * 0.225)
GREEN, LIGHT = (118, 214, 40), (196, 255, 130)

# The bolt on a 16x16 grid, traced as a polygon; pixel blocks are sampled from it.
GRID = 16
BOLT_OUTLINE = [(8, 0), (14, 0), (10, 5), (14, 5), (13, 7), (12, 7), (4, 16), (2, 16), (7, 7), (2, 7),
                (3, 5), (4, 5)]
CELL = (S - 2 * INSET) * 0.72 / GRID
OFFSET = (S - GRID * CELL) / 2
# (start, end, block size) along the bottom-left -> top-right diagonal; past the last band it is smooth.
BANDS = [(0.0, 0.42, CELL * 2), (0.42, 0.52, CELL), (0.52, 0.60, CELL / 2)]
SMOOTH_FROM = 0.60
PIXEL_GAP = 0.07


def _gradient(top: tuple[int, ...], bottom: tuple[int, ...]) -> Image.Image:
    strip = Image.new("RGBA", (1, S))
    for y in range(S):
        t = y / (S - 1)
        strip.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return strip.resize((S, S))


def _masked(layer: Image.Image, mask: Image.Image) -> Image.Image:
    out = layer.copy()
    out.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    return out


def _tile() -> Image.Image:
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((INSET, INSET, S - INSET, S - INSET), radius=TILE_RADIUS, fill=255)
    tile = _masked(_gradient((30, 32, 30, 255), (8, 10, 8, 255)), mask)
    edge = ImageChops.subtract(mask, mask.filter(ImageFilter.MinFilter(7)))
    tile.alpha_composite(_masked(_gradient((255, 255, 255, 90), (255, 255, 255, 10)), edge))
    return tile


def _bolt() -> Image.Image:
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).polygon([(OFFSET + x * CELL, OFFSET + y * CELL) for x, y in BOLT_OUTLINE], fill=255)
    return mask


def _diagonal(x: float, y: float) -> float:
    """0 at the bottom-left corner, 1 at the top-right."""
    return (x + (S - y)) / (2 * S)


def _glow(image: Image.Image, mask: Image.Image) -> None:
    alpha = mask.filter(ImageFilter.GaussianBlur(60)).point(lambda v: v // 2)
    layer = Image.new("RGBA", (S, S), GREEN + (255,))
    layer.putalpha(alpha)
    image.alpha_composite(layer)


def _pixels(bolt: Image.Image) -> Image.Image:
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for start, end, size in BANDS:
        steps = int(S / size) + 1
        for row in range(-2, steps):
            for col in range(-2, steps):
                x, y = OFFSET + col * size, OFFSET + row * size
                cx, cy = x + size / 2, y + size / 2
                if not (0 <= cx < S and 0 <= cy < S) or not start <= _diagonal(cx, cy) < end:
                    continue
                if bolt.getpixel((int(cx), int(cy))):
                    gap = size * PIXEL_GAP
                    draw.rectangle((x + gap, y + gap, x + size - gap, y + size - gap), fill=GREEN + (255,))
    return layer


def _smooth_part(bolt: Image.Image) -> Image.Image:
    region = Image.new("L", (S, S), 0)
    draw = ImageDraw.Draw(region)
    for y in range(S):
        x_from = int(2 * S * SMOOTH_FROM - (S - y))
        if x_from < S:
            draw.line((max(0, x_from), y, S, y), fill=255)
    return _masked(_gradient(LIGHT + (255,), GREEN + (255,)), ImageChops.multiply(bolt, region))


def draw_icon() -> Image.Image:
    bolt = _bolt()
    icon = _tile()
    _glow(icon, bolt)
    icon.alpha_composite(_pixels(bolt))
    icon.alpha_composite(_smooth_part(bolt))
    return icon


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    icon = draw_icon().resize((256, 256), Image.LANCZOS)
    icon.save(ASSETS / "icon.png")
    icon.save(ASSETS / "icon.ico", sizes=ICO_SIZES)
    print(f"Saved {ASSETS / 'icon.png'} and icon.ico")


if __name__ == "__main__":
    main()
