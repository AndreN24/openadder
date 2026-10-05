"""Draws the OpenAdder icon (a pixel-art mouse) into assets/openadder.ico.

Run after a change:  py tools/build_icon.py   (needs Pillow, see requirements-dev.txt)
Every size is the same 16 x 16 pixel drawing, scaled by a whole number, so it stays sharp.
"""

from pathlib import Path

from PIL import Image

OUT = Path(__file__).resolve().parent.parent / "assets" / "openadder.ico"

# T = dark tile, o = green outline, f = body, w = scroll wheel, . = transparent corner
PIXELS = [
    ".TTTTTTTTTTTTTT.",
    "TTTTTTooooTTTTTT",
    "TTTTTofwwfoTTTTT",
    "TTTToffwwffoTTTT",
    "TTTToffwwffoTTTT",
    "TTTToooooooo" + "TTTT",
    "TTTToffffffoTTTT",
    "TTTToffffffoTTTT",
    "TTTToffffffoTTTT",
    "TTTToffffffoTTTT",
    "TTTToffffffoTTTT",
    "TTTToffffffoTTTT",
    "TTTTToffffoTTTTT",
    "TTTTTTooooTTTTTT",
    "TTTTTTTTTTTTTTTT",
    ".TTTTTTTTTTTTTT.",
]
COLORS = {"T": (11, 15, 11, 255), "o": (68, 214, 44, 255), "f": (20, 48, 26, 255),
          "w": (180, 255, 160, 255), ".": (0, 0, 0, 0)}


def drawing() -> Image.Image:
    img = Image.new("RGBA", (16, 16))
    for y, row in enumerate(PIXELS):
        assert len(row) == 16, f"row {y} has {len(row)} pixels"
        for x, ch in enumerate(row):
            img.putpixel((x, y), COLORS[ch])
    return img


if __name__ == "__main__":
    base = drawing()
    sizes = [16, 32, 48, 64, 128, 256]
    images = [base.resize((s, s), Image.NEAREST) for s in sizes]
    images[-1].save(OUT, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[:-1])
    print(f"wrote {OUT}")
