import os
import queue
import unittest
from unittest import mock

from openadder import remap as r


def info(mouse_data=0, x=-32000, y=-32000, injected=False):
    """A hook event far off-screen (so it is never inside OpenAdder's own window)."""
    s = r.MSLLHOOKSTRUCT()
    s.pt.x, s.pt.y = x, y
    s.mouseData = mouse_data
    s.flags = r.LLMHF_INJECTED if injected else 0
    return s


class Mapping(unittest.TestCase):
    def setUp(self):
        self.rm = r.Remapper()
        self.rm._queue = queue.Queue()  # the worker keeps waiting on the old queue
        self.rm._map = {b: "default" for b in r.ALL_BUTTONS}

    def drain(self):
        items = []
        while not self.rm._queue.empty():
            items.append(self.rm._queue.get())
        return items

    def test_default_buttons_pass_through(self):
        self.assertFalse(self.rm._handle(r.WM_LBUTTONDOWN, info()))
        self.assertFalse(self.rm._handle(r.WM_XBUTTONDOWN, info(r.XBUTTON1 << 16)))
        self.assertEqual(self.drain(), [])

    def test_press_and_release_are_blocked_and_paired(self):
        self.rm._map["rear"] = "keys:ctrl+c"
        self.assertTrue(self.rm._handle(r.WM_XBUTTONDOWN, info(r.XBUTTON1 << 16)))
        self.rm._map["rear"] = "default"  # changed while held: the release still matches
        self.assertTrue(self.rm._handle(r.WM_XBUTTONUP, info(r.XBUTTON1 << 16)))
        self.assertEqual(self.drain(), [("keys:ctrl+c", True), ("keys:ctrl+c", False)])

    def test_release_without_blocked_press_passes(self):
        self.assertFalse(self.rm._handle(r.WM_RBUTTONUP, info()))

    def test_front_and_mouse_buttons(self):
        self.rm._map.update(front="mouse:middle", left="mouse:right", middle="disabled")
        self.assertTrue(self.rm._handle(r.WM_XBUTTONDOWN, info(r.XBUTTON2 << 16)))
        self.assertTrue(self.rm._handle(r.WM_LBUTTONDOWN, info()))
        self.assertTrue(self.rm._handle(r.WM_MBUTTONDOWN, info()))
        self.assertEqual([a for a, _ in self.drain()], ["mouse:middle", "mouse:right", "disabled"])

    def test_wheel_sends_one_action_per_notch(self):
        self.rm._map["wheel_down"] = "keys:volume_down"
        delta = (-240) & 0xFFFF
        self.assertTrue(self.rm._handle(r.WM_MOUSEWHEEL, info(delta << 16)))
        self.assertEqual(self.drain(), [("keys:volume_down", True), ("keys:volume_down", False)] * 2)
        self.assertFalse(self.rm._handle(r.WM_MOUSEWHEEL, info(120 << 16)))  # wheel up: default

    def test_clicks_in_own_window_are_never_changed(self):
        self.rm._map["left"] = "mouse:right"
        with mock.patch.object(r, "_point_in_own_window", return_value=True):
            self.assertFalse(self.rm._handle(r.WM_LBUTTONDOWN, info()))

    def test_injected_events_are_ignored(self):
        self.rm._map["left"] = "mouse:right"
        with mock.patch.object(r.user32, "CallNextHookEx", return_value=0) as nxt:
            event = info(injected=True)
            ptr = r.ctypes.addressof(event)
            self.assertEqual(self.rm._callback(r.HC_ACTION, r.WM_LBUTTONDOWN, ptr), 0)
            nxt.assert_called_once()
        self.assertEqual(self.drain(), [])

    def test_driver_buttons_use_their_default_job(self):
        self.rm.external_event("dpi_up", True)
        self.rm.external_event("dpi_up", False)
        self.rm._map["profile"] = "profile:next"
        self.rm.external_event("profile", True)
        self.assertEqual(self.drain(), [("dpi:up", True), ("dpi:up", False), ("profile:next", True)])

    def test_set_mapping_installs_the_hook_only_when_needed(self):
        with mock.patch.object(self.rm, "_start_hook") as start, \
                mock.patch.object(self.rm, "_stop_hook") as stop:
            self.rm.set_mapping({"dpi_up": "dpi:cycle"})
            start.assert_not_called()
            stop.assert_called_once()
            self.rm.set_mapping({"rear": "keys:a"})
            start.assert_called_once()
            self.assertEqual(self.rm._map["left"], "default")
        with self.assertRaises(ValueError):
            self.rm.set_mapping({"rear": "keys:nope"})


@unittest.skipIf(os.environ.get("CI"), "needs a Windows desktop session")
class RealHook(unittest.TestCase):
    def test_install_and_remove(self):
        rm = r.Remapper()
        rm._start_hook()
        try:
            self.assertTrue(rm.hook_active)
            self.assertTrue(rm._hook)  # Windows accepted the hook
            rm._start_hook()           # a second start does nothing
        finally:
            rm.stop()
        self.assertFalse(rm.hook_active)


class Perform(unittest.TestCase):
    def setUp(self):
        self.dpi, self.prof = [], []
        self.rm = r.Remapper(dpi_handler=lambda a, p: self.dpi.append((a, p)),
                             profile_handler=self.prof.append)

    def test_actions_reach_the_right_output(self):
        with mock.patch.object(r, "send_keys") as keys, mock.patch.object(r, "send_mouse") as mouse:
            self.rm._perform("keys:ctrl+c", True)
            keys.assert_called_once_with([0x11, 0x43], up=False)
            self.rm._perform("mouse:back", False)
            mouse.assert_called_once_with("back", up=True)
            self.rm._perform("disabled", True)
        with mock.patch.object(r.os, "startfile") as start:
            self.rm._perform(r"run:C:\x\y.bat", True)
            self.rm._perform(r"run:C:\x\y.bat", False)  # starts on press only
            start.assert_called_once_with(r"C:\x\y.bat")
        self.rm._perform("dpi:sniper", True)
        self.rm._perform("profile:next", True)
        self.rm._perform("profile:next", False)  # profile switches on press only
        self.assertEqual(self.dpi, [("sniper", True)])
        self.assertEqual(self.prof, ["next"])

    def test_inputs_are_built_correctly(self):
        sent = []
        with mock.patch.object(r, "_send", side_effect=lambda inputs: sent.extend(inputs)):
            r.send_keys([0x11, 0x26], up=True)       # released in reverse order
            r.send_mouse("forward", up=False)
            r.send_mouse("wheel_down", up=False)
            r.send_mouse("wheel_down", up=True)      # a scroll step has no release
        self.assertEqual([i.u.ki.wVk for i in sent[:2]], [0x26, 0x11])
        self.assertTrue(sent[0].u.ki.dwFlags & r.KEYEVENTF_EXTENDEDKEY)  # arrow key
        self.assertTrue(sent[1].u.ki.dwFlags & r.KEYEVENTF_KEYUP)
        self.assertEqual((sent[2].u.mi.dwFlags, sent[2].u.mi.mouseData), (r.MOUSEEVENTF_XDOWN, 2))
        self.assertEqual(sent[3].u.mi.mouseData, (-120) & 0xFFFFFFFF)
        self.assertEqual(len(sent), 4)


class Keys(unittest.TestCase):
    def test_parse_keys(self):
        self.assertEqual(r.parse_keys("ctrl+shift+t"), [0x11, 0x10, 0x54])
        self.assertEqual(r.parse_keys("F5"), [0x74])
        for bad in ("ctrl+nope", "", "+"):
            with self.assertRaises(ValueError):
                r.parse_keys(bad)

    def test_validate_action(self):
        for ok in ("default", "disabled", "keys:ctrl+c", "mouse:middle", "dpi:sniper",
                   "dpi:up", "mouse:wheel_down", "profile:next"):
            r.validate_action(ok)
        for bad in ("keys:", "mouse:side", "dpi:sideways", "profile:last", "jump"):
            with self.assertRaises(ValueError):
                r.validate_action(bad)


if __name__ == "__main__":
    unittest.main()
