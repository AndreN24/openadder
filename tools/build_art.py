"""Renders the DeathAdder V2 picture into PNG files in openadder/assets/art.

Run this after a change to the drawing:  py tools/build_art.py

The heavy work (4x supersampling, blur) happens here, once, so the app itself
only loads small PNG files.
Needs Python 3 and Pillow (only to build the art, not to run the app). The outline geometry is adapted from Snakecharmer's
DeathAdder Elite diagram (https://github.com/asavs/snakecharmer,
GPL-2.0-or-later). The Elite and the V2 share the same shell and button layout.
"""

import base64
import colorsys
import json
import zlib
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ART_DIR = Path(__file__).resolve().parent.parent / "openadder" / "assets" / "art"
SCALE = 1.12           # display pixels per design unit
ORIGIN = (104, -18)    # design coordinate of the image's top-left corner
SIZE = (248, 462)      # design units shown
ACCENT = (68, 214, 44)
# Hit-test order: small parts first. Must match openadder/mouse_art.py.
HIT_ORDER = ("dpi_up", "dpi_down", "front", "rear", "wheel_up", "wheel_down", "middle",
             "profile", "left", "right")

SS = 4                 # supersampling factor for smooth edges

BODY = [(214, 30), [
    ((174, 39), (141, 58), (126, 73)), ((130, 90), (134, 108), (137, 129)),
    ((141, 152), (143, 178), (140, 205)), ((137, 225), (133, 249), (133, 274)),
    ((133, 312), (144, 342), (164, 361)), ((181, 377), (202, 386), (225, 389)),
    ((256, 389), (283, 379), (302, 361)), ((332, 341), (332, 310), (332, 273)),
    ((326, 248), (332, 224), (323, 204)), ((317, 179), (316, 154), (318, 130)),
    ((319, 111), (323, 91), (326, 73)), ((311, 58), (278, 39), (242, 30)),
    ((242, 62), (242, 92), (242, 122)), ((242, 134), (214, 134), (214, 122)),
    ((214, 92), (214, 62), (214, 30)),
]]
LEFT_GRIP = [(129, 76), [
    ((134, 94), (138, 107), (142, 121)), ((147, 135), (151, 152), (153, 170)),
    ((155, 189), (155, 209), (151, 225)), ((148, 236), (145, 245), (142, 253)),
]]
RIGHT_GRIP = [(326, 73), [
    ((323, 97), (321, 118), (319, 141)), ((318, 167), (321, 192), (325, 215)),
    ((328, 233), (331, 251), (331, 273)), ((327, 264), (324, 251), (322, 237)),
    ((319, 213), (317, 189), (317, 165)), ((317, 132), (320, 99), (326, 73)),
]]
FRONT_SIDE = [(143, 140), [
    ((143, 155), (143, 170), (142, 185)), ((142, 185), (152, 185), (152, 185)),
    ((151, 170), (149, 155), (147, 140)), ((147, 140), (143, 140), (143, 140)),
]]
REAR_SIDE = [(152, 187), [
    ((152, 187), (142, 187), (142, 187)), ((141, 205), (140, 222), (138, 238)),
    ((138, 238), (143, 238), (143, 238)), ((148, 222), (151, 205), (152, 187)),
]]
# Seam between the main buttons and the palm rest (left half, mirrored for the right).
SEAM_LEFT = [(136, 236), [((175, 228), (205, 224), (228, 223))]]
SEAM_RIGHT = [(228, 223), [((251, 224), (281, 228), (326, 236))]]

WHEEL_ZONE = (214, 65, 241, 131)
WHEEL = (218, 67, 238, 130)
DPI_UP = (222, 140, 235, 170)
DPI_DOWN = (222, 172, 235, 201)
LOGO = (204, 276, 252, 324)
PROFILE_PILL = (180, 412, 276, 436)
CHIP_UP = (250, 66, 264, 80)       # small arrow markers for scroll up / down
CHIP_DOWN = (250, 117, 264, 131)
CABLE_SLOT = (214, 26, 242, 70)

# Parts that get a thin outline so it is clear they are clickable.
OUTLINED = ("middle", "front", "rear", "dpi_up", "dpi_down", "profile", "chip_up", "chip_down")



def _bezier(path, steps=24):
    (x, y), curves = path
    pts = [(x, y)]
    for c1, c2, end in curves:
        x0, y0 = pts[-1]
        for i in range(1, steps + 1):
            t = i / steps
            u = 1 - t
            px = u**3 * x0 + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * end[0]
            py = u**3 * y0 + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * end[1]
            pts.append((px, py))
    return pts


def _xy(x, y):
    return ((x - ORIGIN[0]) * SCALE * SS, (y - ORIGIN[1]) * SCALE * SS)


def _pts(points):
    return [_xy(x, y) for x, y in points]


def _box(b):
    return [*_xy(b[0], b[1]), *_xy(b[2], b[3])]


def _w(units):
    return max(1, round(units * SCALE * SS))


class ArtBuilder:
    def __init__(self):
        self.size = (round(SIZE[0] * SCALE), round(SIZE[1] * SCALE))
        self._big = (self.size[0] * SS, self.size[1] * SS)
        self._build_masks()
        self._build_layers()

    # --- geometry -------------------------------------------------------------

    def _mask(self, draw_fn):
        m = Image.new("L", self._big, 0)
        draw_fn(ImageDraw.Draw(m))
        return m

    def _small(self, big_mask):
        return big_mask.resize(self.size, Image.LANCZOS)

    def _build_masks(self):
        body = self._mask(lambda d: d.polygon(_pts(_bezier(BODY)), fill=255))
        upper = self._mask(lambda d: d.polygon(
            _pts([(100, 0)] + _bezier(SEAM_LEFT) + _bezier(SEAM_RIGHT)[1:] + [(360, 0)]), fill=255))
        left_half = self._mask(lambda d: d.rectangle(_box((0, -50, 228, 500)), fill=255))
        buttons = ImageChops.multiply(body, upper)
        wheel_zone = self._mask(lambda d: d.rounded_rectangle(_box(WHEEL_ZONE), radius=_w(10), fill=255))
        w_mid = (WHEEL_ZONE[1] + WHEEL_ZONE[3]) / 2

        self._big_masks = {
            "body": body,
            "left": ImageChops.multiply(buttons, left_half),
            "right": ImageChops.subtract(buttons, left_half),
            "middle": wheel_zone,
            "wheel_up": ImageChops.multiply(wheel_zone, self._mask(
                lambda d: d.rectangle(_box((0, -50, 400, w_mid)), fill=255))),
            "wheel_down": ImageChops.multiply(wheel_zone, self._mask(
                lambda d: d.rectangle(_box((0, w_mid, 400, 500)), fill=255))),
            "front": self._mask(lambda d: d.polygon(_pts(_bezier(FRONT_SIDE)), fill=255)),
            "rear": self._mask(lambda d: d.polygon(_pts(_bezier(REAR_SIDE)), fill=255)),
            "dpi_up": self._mask(lambda d: d.rounded_rectangle(_box(DPI_UP), radius=_w(4), fill=255)),
            "dpi_down": self._mask(lambda d: d.rounded_rectangle(_box(DPI_DOWN), radius=_w(4), fill=255)),
            "profile": self._mask(lambda d: d.rounded_rectangle(_box(PROFILE_PILL), radius=_w(12), fill=255)),
            "logo": self._mask(lambda d: d.ellipse(_box(LOGO), fill=255)),
            "chip_up": self._mask(lambda d: d.ellipse(_box(CHIP_UP), fill=255)),
            "chip_down": self._mask(lambda d: d.ellipse(_box(CHIP_DOWN), fill=255)),
        }
        for key, chip in (("wheel_up", "chip_up"), ("wheel_down", "chip_down")):
            self._big_masks[key] = ImageChops.lighter(self._big_masks[key], self._big_masks[chip])
        self.masks = {k: self._small(v) for k, v in self._big_masks.items()}
        # Side buttons are thin: use a wider mask for hovering and clicking.
        self._hit_masks = dict(self.masks)
        self._hit_masks["wheel_up"] = self.masks["chip_up"].filter(ImageFilter.MaxFilter(5))
        self._hit_masks["wheel_down"] = self.masks["chip_down"].filter(ImageFilter.MaxFilter(5))
        for key in ("front", "rear"):
            self._hit_masks[key] = self.masks[key].filter(ImageFilter.MaxFilter(7))

    # --- layers ---------------------------------------------------------------

    def _build_layers(self):
        big = self._big
        body = self._big_masks["body"]

        # Shadow + body with a soft vertical gradient.
        below = Image.new("RGBA", big, (0, 0, 0, 0))
        shadow = Image.new("RGBA", big, (0, 0, 0, 255))
        shadow.putalpha(body.point(lambda v: v * 0.45).filter(ImageFilter.GaussianBlur(_w(7))))
        below.alpha_composite(shadow, (0, _w(5)))

        grad = Image.linear_gradient("L").resize(big)
        top_col, bottom_col = (60, 63, 69), (32, 34, 38)
        fill = Image.merge("RGB", [
            grad.point(lambda v, a=a, b=b: round(a + (b - a) * v / 255))
            for a, b in zip(top_col, bottom_col)]).convert("RGBA")
        fill.putalpha(body)
        below.alpha_composite(fill)

        # Soft highlight on the upper left of the shell.
        glow = Image.new("L", big, 0)
        ImageDraw.Draw(glow).ellipse(_box((120, 40, 260, 260)), fill=40)
        glow = ImageChops.multiply(glow.filter(ImageFilter.GaussianBlur(_w(30))), body)
        white = Image.new("RGBA", big, (255, 255, 255, 0))
        white.putalpha(glow)
        below.alpha_composite(white)

        d = ImageDraw.Draw(below)
        line, seam, part = (84, 88, 96, 255), (20, 21, 24, 255), (44, 46, 51, 255)

        # Grips and seams.
        d.polygon(_pts(_bezier(RIGHT_GRIP)), fill=(27, 28, 31, 255))
        d.line(_pts(_bezier(LEFT_GRIP)), fill=(27, 28, 31, 255), width=_w(2), joint="curve")
        d.line(_pts(_bezier(SEAM_LEFT) + _bezier(SEAM_RIGHT)[1:]), fill=seam, width=_w(1.4),
               joint="curve")
        d.line(_pts([(228, 131), (228, 140)]), fill=seam, width=_w(1.4))
        d.line(_pts([(228, 201), (228, 223)]), fill=seam, width=_w(1.4))
        d.polygon(_pts(_bezier(BODY)), outline=line, width=_w(1.2))

        # Dark channel behind the wheel, and the cable boot.
        d.rectangle(_box(CABLE_SLOT), fill=(24, 25, 28, 255))
        d.rounded_rectangle(_box((220, 10, 236, 30)), radius=_w(2), fill=(30, 31, 34, 255))
        d.line(_pts([(228, -18), (228, 10)]), fill=(30, 31, 34, 255), width=_w(4))

        # DPI buttons, side buttons, profile pill.
        for box in (DPI_UP, DPI_DOWN):
            d.rounded_rectangle(_box(box), radius=_w(4), fill=part, outline=line, width=_w(1))
        for path in (FRONT_SIDE, REAR_SIDE):
            d.polygon(_pts(_bezier(path)), fill=(66, 69, 76, 255), outline=(98, 102, 110, 255),
                      width=_w(1))
        d.rounded_rectangle(_box(PROFILE_PILL), radius=_w(12), fill=(44, 46, 51, 255),
                            outline=line, width=_w(1))
        for box, up in ((CHIP_UP, True), (CHIP_DOWN, False)):
            d.ellipse(_box(box), fill=part, outline=line, width=_w(1))
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            tri = [(cx - 3.2, cy + 1.6), (cx + 3.2, cy + 1.6), (cx, cy - 2.4)] if up else                   [(cx - 3.2, cy - 1.6), (cx + 3.2, cy - 1.6), (cx, cy + 2.4)]
            d.polygon(_pts(tri), fill=(170, 175, 182, 255))
        self._below = below.resize(self.size, Image.LANCZOS)

        # Thin accent outline around every clickable part.
        edge = Image.new("L", self.size, 0)
        for key in OUTLINED:
            m = self.masks[key]
            edge = ImageChops.lighter(edge, ImageChops.subtract(m.filter(ImageFilter.MaxFilter(3)), m))
        self._outline = edge.point(lambda v: v * 0.8)

        # Top layer: wheel details drawn over the lighting colour.
        top = Image.new("RGBA", big, (0, 0, 0, 0))
        d = ImageDraw.Draw(top)
        d.rounded_rectangle(_box(WHEEL), radius=_w(8), fill=(36, 38, 42, 255))
        for y in range(75, 126, 10):
            d.line(_pts([(221, y), (235, y)]), fill=(58, 61, 67, 255), width=_w(1.3))
        self._top = top.resize(self.size, Image.LANCZOS)

        # Lighting zone: the visible ring of the wheel with a soft glow. The logo is not drawn.
        ring = ImageChops.subtract(self._big_masks["middle"], self._mask(
            lambda dd: dd.rounded_rectangle(_box(WHEEL), radius=_w(8), fill=255)))
        self._zone_masks = {
            "wheel": (self._small(ring),
                      self._small(ring.filter(ImageFilter.GaussianBlur(_w(6)))).point(lambda v: v * 0.55)),
        }

        hue = Image.new("RGBA", self.size)
        px = hue.load()
        for y in range(self.size[1]):
            r, g, b = colorsys.hsv_to_rgb((y / self.size[1] * 3) % 1, 0.8, 1.0)
            for x in range(self.size[0]):
                px[x, y] = (int(r * 255), int(g * 255), int(b * 255), 255)
        self._spectrum = hue

    # --- export ---------------------------------------------------------------

    def export(self, out: Path):
        """Writes what the app needs, so the app itself needs no image library:

        * cropped PNG layers that Tk loads directly and stacks on a canvas,
        * art.json: where each layer goes, the lighting zones (alpha and spectrum
          colours, for tinting at run time), and the hit map.
        """
        out.mkdir(parents=True, exist_ok=True)
        for old in list(out.glob("*.png")) + list(out.glob("*.json")):
            old.unlink()
        layers = {}

        def save(name, image):
            box = image.getchannel("A").getbbox() or (0, 0, 1, 1)
            image.crop(box).save(out / f"{name}.png", optimize=True)
            layers[name] = box[:2]

        def rgba(color, alpha):
            layer = Image.new("RGBA", self.size, (*color, 255))
            layer.putalpha(alpha)
            return layer

        def packed(data: bytes) -> str:
            return base64.b64encode(zlib.compress(data, 9)).decode("ascii")

        save("below", self._below)
        save("top", self._top)
        save("outline", rgba(ACCENT, self._outline))
        for key in HIT_ORDER:
            save(f"hl_{key}", rgba(ACCENT, self.masks[key].point(lambda v: round(v * 0.45))))

        zones = {}
        for zone, (sharp, soft) in self._zone_masks.items():
            save(f"zone_{zone}_off", rgba((30, 31, 34), sharp))
            both = ImageChops.screen(sharp, soft)  # 1 - (1 - a)(1 - b)
            box = both.getbbox()
            zones[zone] = {"offset": box[:2], "size": [box[2] - box[0], box[3] - box[1]],
                           "alpha": packed(both.crop(box).tobytes()),
                           "spectrum": packed(self._spectrum.convert("RGB").crop(box).tobytes())}

        # Hit map: one byte per pixel = 1 + index in HIT_ORDER (0 = nothing).
        hitmap = Image.new("L", self.size, 0)
        for i in reversed(range(len(HIT_ORDER))):
            m = self._hit_masks[HIT_ORDER[i]].point(lambda v: 255 if v > 100 else 0)
            hitmap.paste(i + 1, mask=m)

        manifest = {"size": list(self.size), "hit_order": list(HIT_ORDER), "layers": layers,
                    "zones": zones, "hitmap": packed(hitmap.tobytes())}
        (out / "art.json").write_text(json.dumps(manifest), encoding="utf-8")


if __name__ == "__main__":
    ArtBuilder().export(ART_DIR)
    print(f"wrote {ART_DIR}")
