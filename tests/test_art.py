import base64
import tkinter as tk
import unittest

from openadder import models
from openadder.mouse_art import MouseView, design_to_px, png_rgba, tint

V2_BUTTONS = models.DEFAULT.buttons


class PngWriter(unittest.TestCase):
    def test_tk_reads_the_png_we_write(self):
        root = tk.Tk()
        root.update()
        self.addCleanup(root.destroy)
        pixels = bytes([255, 0, 0, 255, 0, 255, 0, 128,
                        0, 0, 255, 255, 10, 20, 30, 0])
        img = tk.PhotoImage(master=root, format="png", data=base64.b64encode(png_rgba(2, 2, pixels)))
        self.assertEqual((img.width(), img.height()), (2, 2))
        self.assertEqual(img.get(0, 0), (255, 0, 0))
        self.assertEqual(img.get(0, 1), (0, 0, 255))
        self.assertTrue(img.transparency_get(1, 1))

    def test_tint(self):
        self.assertEqual(tint(bytes([0, 255]), 0.5, color=(1, 2, 3)), bytes([1, 2, 3, 0, 1, 2, 3, 128]))
        self.assertEqual(tint(bytes([200]), 2.0, spectrum=bytes([9, 8, 7])), bytes([9, 8, 7, 255]))


class View(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.update()
        cls.canvas = tk.Canvas(cls.root)
        cls.view = MouseView(cls.canvas, V2_BUTTONS)

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def visible(self):
        return [i for i in self.canvas.find_all() if self.canvas.itemcget(i, "state") != "hidden"]

    def test_hit_test(self):
        hit = self.view.hit
        self.assertEqual(hit(*design_to_px(228, 155)), "dpi_up")
        self.assertEqual(hit(*design_to_px(228, 186)), "dpi_down")
        self.assertEqual(hit(*design_to_px(228, 100)), "middle")
        self.assertEqual(hit(*design_to_px(257, 73)), "wheel_up")
        self.assertEqual(hit(*design_to_px(257, 124)), "wheel_down")
        self.assertEqual(hit(*design_to_px(228, 424)), "profile")
        self.assertEqual(hit(*design_to_px(180, 120)), "left")
        self.assertEqual(hit(*design_to_px(280, 120)), "right")
        self.assertIsNone(hit(2, 2))
        self.assertIsNone(hit(-5, 9999))

    def test_every_button_can_be_hit(self):
        w, h = self.view.size
        found = {self.view.hit(x, y) for x in range(0, w, 2) for y in range(0, h, 2)}
        self.assertEqual(found - {None}, set(self.view.hit_order))

    def test_only_one_highlight(self):
        before = len(self.visible())
        self.view.set_highlight("left")
        self.view.set_highlight("rear")
        self.assertEqual(len(self.visible()), before + 1)
        self.view.set_highlight()
        self.assertEqual(len(self.visible()), before)

    def test_lighting_tints_the_zone(self):
        self.view.set_lighting({"logo": ("static", (0, 255, 0), 255), "wheel": ("static", (0, 255, 0), 255)})
        img = self.view._zone_images["wheel"]
        z = self.view._zones["wheel"]
        x, y = (int(v) for v in design_to_px(215, 100))  # left edge of the wheel ring
        self.assertEqual(img.get(x - z["offset"][0], y - z["offset"][1]), (0, 255, 0))
        self.assertNotIn("logo", self.view._zone_images)  # the logo is not drawn
        self.view.set_lighting({"logo": ("off", (0, 0, 0), 0), "wheel": ("off", (0, 0, 0), 9)})
        self.assertEqual(self.canvas.itemcget(self.view._zone_items["wheel"][1], "state"), "hidden")

    def test_buttons_the_mouse_does_not_have_are_not_drawn(self):
        canvas = tk.Canvas(self.root)
        self.addCleanup(canvas.destroy)
        view = MouseView(canvas, models.BASIC_BUTTONS)
        self.addCleanup(view.destroy)
        self.assertIsNone(view.hit(*design_to_px(228, 155)))  # no DPI buttons
        self.assertIsNone(view.hit(*design_to_px(228, 424)))  # no profile button
        self.assertEqual(view.hit(*design_to_px(180, 120)), "left")
        self.assertNotIn("part_dpi", view._images)
        self.assertNotIn("hl_profile", view._images)
        self.assertEqual(len(canvas.find_all()), len(self.canvas.find_all()) - 2)

    def test_destroy_frees_everything(self):
        canvas = tk.Canvas(self.root)
        view = MouseView(canvas, V2_BUTTONS)
        self.addCleanup(canvas.destroy)
        view.set_lighting({"logo": ("static", (1, 2, 3), 255), "wheel": ("spectrum", (0, 0, 0), 255)})
        view.destroy()
        self.assertEqual(canvas.find_all(), ())
        self.assertEqual(view._images, {})


if __name__ == "__main__":
    unittest.main()
