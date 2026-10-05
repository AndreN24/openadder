import unittest

from openadder import actions as a
from openadder.remap import parse_keys, validate_action


class Catalog(unittest.TestCase):
    def test_every_catalog_action_is_valid_and_explained(self):
        for _category, items in a.CATALOG:
            for item_label, action in items:
                validate_action(action)
                self.assertEqual(a.label("rear", action), item_label)
                self.assertTrue(a.describe("rear", action).endswith("."), action)

    def test_default_and_disabled(self):
        for key, _name, what in a.BUTTONS:
            self.assertEqual(a.label(key, "default"), f"Default ({what})")
            self.assertEqual(a.describe(key, "default"), f"Does its normal job: {what}.")
        self.assertEqual(a.label("rear", "disabled"), "Disabled")
        self.assertEqual(a.describe("rear", "disabled"), "Does nothing.")

    def test_recorded_keys(self):
        self.assertEqual(a.label("rear", "keys:ctrl+shift+t"), "Ctrl+Shift+T")
        self.assertEqual(a.describe("rear", "keys:ctrl+shift+t"), "Presses Ctrl+Shift+T.")
        self.assertEqual(a.pretty_keys("alt+f4"), "Alt+F4")
        self.assertEqual(a.pretty_keys("tab"), "Tab")
        self.assertEqual(a.pretty_keys("win+pageup"), "Win+Page Up")


class RunProgram(unittest.TestCase):
    def test_label_and_description(self):
        self.assertEqual(a.label("rear", r"run:C:\Tools\backup.bat"), "Run: backup.bat")
        self.assertEqual(a.describe("rear", "run:C:/Tools/notes.txt"), "Starts notes.txt.")
        validate_action(r"run:C:\x.exe")
        with self.assertRaises(ValueError):
            validate_action("run: ")


class Recording(unittest.TestCase):
    def test_keysym_to_name(self):
        self.assertEqual(a.keysym_to_name("Control_L"), "ctrl")
        self.assertEqual(a.keysym_to_name("Prior"), "pageup")
        self.assertEqual(a.keysym_to_name("T"), "t")
        self.assertEqual(a.keysym_to_name("7"), "7")
        self.assertEqual(a.keysym_to_name("F12"), "f12")
        self.assertIsNone(a.keysym_to_name("F25"))
        self.assertIsNone(a.keysym_to_name("XF86AudioRaiseVolume"))

    def test_combo_puts_modifiers_first(self):
        self.assertEqual(a.combo(["t", "shift", "ctrl"]), "ctrl+shift+t")
        self.assertEqual(a.combo(["alt", "f4"]), "alt+f4")

    def test_every_recordable_key_can_be_sent(self):
        for keysym, name in a._KEYSYMS.items():
            parse_keys(name)
        for name in "a z 0 9 f1 f24".split():
            parse_keys(name)


if __name__ == "__main__":
    unittest.main()
