import os
import time
import unittest
from unittest import mock

from openadder import tray as t
from openadder.gui import ICON


class Menu(unittest.TestCase):
    def test_menu_items_get_command_ids(self):
        calls = []
        items = [t.MenuItem("Open", lambda: calls.append("open"), default=True),
                 t.MenuItem("Profile", [t.MenuItem("A", lambda: calls.append("a"), checked=True),
                                        t.MenuItem("B", lambda: calls.append("b"))]),
                 t.Separator(),
                 t.MenuItem("Quit", lambda: calls.append("quit"))]
        tray = t.Tray("x", ICON, lambda: None, lambda: items)
        appended = []
        with mock.patch.object(t.user32, "CreatePopupMenu", side_effect=[101, 102]), \
                mock.patch.object(t.user32, "AppendMenuW", side_effect=lambda *a: appended.append(a)):
            actions = []
            tray._build(items, actions)
        ids = {text: ident for _menu, _flags, ident, text in appended if text}
        self.assertEqual(ids["Profile"], 102)  # the submenu handle
        for text in ("Open", "A", "B", "Quit"):
            actions[ids[text] - 1]()
        self.assertEqual(calls, ["open", "a", "b", "quit"])
        flags = {text: f for _menu, f, _ident, text in appended if text}
        self.assertTrue(flags["A"] & t.MF_CHECKED)
        self.assertTrue(flags["Open"] & t.MF_DEFAULT)


@unittest.skipIf(os.environ.get("CI"), "needs a Windows desktop session")
class RealIcon(unittest.TestCase):
    def test_icon_appears_and_goes_away(self):
        clicks = []
        tray = t.Tray("OpenAdder test", ICON, lambda: clicks.append(1), lambda: [])
        tray.start()
        self.assertTrue(tray._hwnd)
        self.assertTrue(tray._icon)  # the .ico file loaded
        tray._wndproc(tray._hwnd, t.WM_TRAY, 0, t.WM_LBUTTONUP)
        self.assertEqual(clicks, [1])
        tray.stop()
        for _ in range(100):
            if not t.user32.IsWindow(tray._hwnd):
                break
            time.sleep(0.02)
        self.assertFalse(t.user32.IsWindow(tray._hwnd))

    def test_global_shortcut(self):
        pressed = []
        tray = t.Tray("OpenAdder test", ICON, lambda: None, lambda: [],
                      hotkey=(t.MOD_CONTROL | t.MOD_ALT | t.MOD_SHIFT, 0x7B),  # F12: free in tests
                      on_hotkey=lambda: pressed.append(1))
        tray.start()
        self.addCleanup(tray.stop)
        self.assertTrue(tray.hotkey_ok)
        tray._wndproc(tray._hwnd, t.WM_HOTKEY, 1, 0)
        self.assertEqual(pressed, [1])


if __name__ == "__main__":
    unittest.main()
