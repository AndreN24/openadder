"""DeathAdder picture, drawn as layers on a Tk canvas. No image library is needed.

tools/build_art.py pre-renders the layers as PNG files (Tk reads PNG itself) and
writes art.json: where each layer goes, the lighting zones and the hit map.
The DPI buttons and the profile button are separate layers, shown only on models that have them.
Only one part is highlighted at a time; changing it only swaps one small layer. A lighting change re-tints one
small zone image with the PNG writer below.
"""

import base64
import json
import struct
import sys
import tkinter as tk
import zlib
from pathlib import Path

SCALE = 1.12           # display pixels per design unit (must match tools/build_art.py)
ORIGIN = (104, -18)    # design coordinate of the image's top-left corner

_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
ART_DIR = _BASE / "openadder" / "assets" / "art"


def design_to_px(x, y):
    return (x - ORIGIN[0]) * SCALE, (y - ORIGIN[1]) * SCALE


def _unpack(text: str) -> bytes:
    return zlib.decompress(base64.b64decode(text))


def png_rgba(width: int, height: int, rgba: bytes) -> bytes:
    """A minimal PNG file (8-bit RGBA, no filter) for the given pixels."""
    stride = width * 4
    raw = b"".join(b"\x00" + rgba[y * stride:(y + 1) * stride] for y in range(height))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data +
                struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


def tint(alpha: bytes, level: float, color=None, spectrum: bytes = None) -> bytes:
    """RGBA pixels: one colour (or the spectrum colours) with the zone's alpha scaled by level."""
    n = len(alpha)
    out = bytearray(n * 4)
    if spectrum is not None:
        out[0::4], out[1::4], out[2::4] = spectrum[0::3], spectrum[1::3], spectrum[2::3]
    else:
        out[0::4], out[1::4], out[2::4] = (bytes([c]) * n for c in color)
    out[3::4] = alpha.translate(bytes(min(255, round(v * level)) for v in range(256)))
    return bytes(out)


class MouseView:
    """Owns the canvas items of the picture. destroy() frees all images.

    buttons: the buttons that the mouse has. Only these are drawn and clickable.
    """

    def __init__(self, canvas: tk.Canvas, buttons, art_dir: Path = ART_DIR):
        self.canvas = canvas
        manifest = json.loads((art_dir / "art.json").read_text(encoding="utf-8"))
        self.size = tuple(manifest["size"])
        self.hit_order = manifest["hit_order"]
        self.buttons = set(buttons)
        parts = [name for name, keys in manifest["parts"].items() if self.buttons & set(keys)]
        unused = set(manifest["parts"]) - set(parts)
        unused |= {f"hl_{key}" for key in self.hit_order if key not in self.buttons}
        self._hitmap = _unpack(manifest["hitmap"])
        self._zones = {z: {"offset": tuple(d["offset"]), "size": tuple(d["size"]),
                           "alpha": _unpack(d["alpha"]), "spectrum": _unpack(d["spectrum"])}
                       for z, d in manifest["zones"].items()}
        self._offsets = {name: tuple(xy) for name, xy in manifest["layers"].items()
                         if name not in unused}
        self._images = {name: tk.PhotoImage(master=canvas, file=str(art_dir / f"{name}.png"))
                        for name in self._offsets}
        self._zone_images = {}
        self._zone_state = {}

        def item(name):
            x, y = self._offsets[name]
            return canvas.create_image(x, y, anchor="nw", image=self._images[name])

        self._items = [item("below")] + [item(name) for name in parts]
        self._zone_items = {}
        for zone, z in self._zones.items():
            off = item(f"zone_{zone}_off")
            lit = canvas.create_image(*z["offset"], anchor="nw", state="hidden")
            self._zone_items[zone] = (off, lit)
            self._items += [off, lit]
        self._items += [item("top"), item("outline")]
        self._hl = canvas.create_image(0, 0, anchor="nw", state="hidden")
        self._items.append(self._hl)

    def hit(self, x, y):
        w, h = self.size
        if not (0 <= x < w and 0 <= y < h):
            return None
        v = self._hitmap[int(y) * w + int(x)]
        key = self.hit_order[v - 1] if 0 < v <= len(self.hit_order) else None
        return key if key in self.buttons else None

    def set_lighting(self, lighting):
        """lighting: {"logo": (effect, (r, g, b), brightness), "wheel": (...)}"""
        for zone, state in lighting.items():
            if zone not in self._zones or self._zone_state.get(zone) == state:
                continue
            self._zone_state[zone] = state
            effect, color, brightness = state
            off, lit = self._zone_items[zone]
            if effect == "off" or brightness <= 0:
                self.canvas.itemconfigure(off, state="normal")
                self.canvas.itemconfigure(lit, state="hidden")
                continue
            z = self._zones[zone]
            level = 0.3 + 0.7 * brightness / 255  # stays visible when dim
            pixels = tint(z["alpha"], level, color=color,
                          spectrum=z["spectrum"] if effect == "spectrum" else None)
            data = base64.b64encode(png_rgba(*z["size"], pixels))
            self._zone_images[zone] = tk.PhotoImage(master=self.canvas, data=data, format="png")
            self.canvas.itemconfigure(lit, image=self._zone_images[zone], state="normal")
            self.canvas.itemconfigure(off, state="hidden")

    def set_highlight(self, key=None):
        """Highlights one button in green, or none."""
        if key is None:
            self.canvas.itemconfigure(self._hl, state="hidden")
            return
        name = f"hl_{key}"
        self.canvas.coords(self._hl, *self._offsets[name])
        self.canvas.itemconfigure(self._hl, image=self._images[name], state="normal")

    def destroy(self):
        for item in self._items:
            self.canvas.delete(item)
        self._images.clear()
        self._zone_images.clear()
