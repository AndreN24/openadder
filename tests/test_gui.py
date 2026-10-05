"""Tests for the window, with a simulated mouse, a fake tray and a temporary settings file.

Nothing here touches the real mouse, the real autostart entry or a real mouse hook.
"""

import time
import unittest
from unittest import mock

from openadder import config, gui
from openadder import protocol as p
from openadder.dialogs import NameDialog, RecordKeysDialog

from .helpers import FakeMouse, TempConfig


REAL_START_TRAY = gui.App._start_tray


class _App(unittest.TestCase):
    real_start_tray = staticmethod(REAL_START_TRAY)

    def setUp(self):
        self.tmp = TempConfig().start()
        self.addCleanup(self.tmp.stop)
        self.mouse = FakeMouse()
        self.listener = mock.Mock()
        self.yes = True
        patches = [
            mock.patch.object(gui.DeathAdderV2, "open", side_effect=lambda: self.mouse),
            mock.patch.object(gui, "ButtonListener", return_value=self.listener),
            mock.patch.object(gui.Remapper, "_start_hook"),
            mock.patch.object(gui.Remapper, "_stop_hook"),
            mock.patch.object(gui.App, "_start_tray", lambda app: setattr(app, "tray", mock.Mock())),
            mock.patch.object(config, "set_autostart"),
            mock.patch.object(config, "refresh_autostart"),
            mock.patch.object(config, "autostart_enabled", return_value=False),
            mock.patch.object(gui.messagebox, "askyesno", side_effect=lambda *a, **k: self.yes),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.app = gui.App(start_minimized=True)
        self.addCleanup(self.app.quit)
        self.pump(lambda: self.app.dev is not None)

    def pump(self, until=lambda: False, seconds=1.5):
        """Runs the window's event loop until until() is true or the time is over."""
        end = time.time() + seconds
        while time.time() < end:
            self.app.root.update()
            if until():
                return True
            time.sleep(0.01)
        return False

    def idle(self, seconds=0.3):
        self.pump(seconds=seconds)


class Connection(_App):
    def test_connect_shows_the_values_of_the_mouse(self):
        self.assertIn("Connected", self.app.conn_label.cget("text"))
        self.assertEqual(self.app.prof["dpi"], {"stages": [400, 800, 1600, 2400, 3200], "active": 2})
        self.assertEqual(self.app.prof["lighting"]["logo"]["brightness"], 168)
        self.assertEqual(self.app.stage_dpi[3].get(), 2400)
        self.assertEqual(self.mouse.calls, [])  # connecting only reads

    def test_lost_mouse_reconnects(self):
        self.app._io(lambda: (_ for _ in ()).throw(OSError("unplugged")))
        self.pump(lambda: self.app.dev is None)
        self.assertIn("disconnected", self.app.conn_label.cget("text"))
        self.assertIn("reconnect", self.app._after)

    def test_mouse_left_in_driver_mode_is_reset(self):
        self.mouse.mode = p.DRIVER_MODE
        self.app.connect()
        self.pump(lambda: ("set_device_mode", (0,)) in self.mouse.calls)
        self.assertIn(("set_device_mode", (0,)), self.mouse.calls)


class Buttons(_App):
    def test_set_action(self):
        self.app.set_action("rear", "keys:ctrl+c")
        self.assertEqual(self.app.prof["buttons"]["rear"], "keys:ctrl+c")
        self.assertEqual(self.app.remapper._map["rear"], "keys:ctrl+c")
        self.assertEqual(self.app.action_buttons["rear"].cget("text"), "Copy")
        self.assertEqual(config.load()["profiles"]["Default"]["buttons"]["rear"], "keys:ctrl+c")

    def test_left_click_asks_first(self):
        self.yes = False
        self.app.set_action("left", "mouse:right")
        self.assertEqual(self.app.prof["buttons"]["left"], "default")
        self.yes = True
        self.app.set_action("left", "mouse:right")
        self.assertEqual(self.app.prof["buttons"]["left"], "mouse:right")

    def test_left_menu_has_no_disabled(self):
        labels = lambda m: [m.entrycget(i, "label") for i in range(m.index("end") + 1)
                            if m.type(i) == "command"]
        self.assertNotIn("Disabled", labels(self.app.action_menus["left"]))
        self.assertIn("Disabled", labels(self.app.action_menus["rear"]))

    def test_clicking_the_picture_opens_the_menu(self):
        self.app.show()
        x, y = (int(v) for v in gui.design_to_px(146, 212))  # rear side button
        with mock.patch.object(self.app.action_menus["rear"], "tk_popup") as popup:
            self.app._on_canvas_click(mock.Mock(x=x, y=y))
        popup.assert_called_once()
        self.assertEqual(self.app._selected, "rear")

    def test_dpi_buttons_turn_driver_mode_on_and_off(self):
        self.app.set_action("dpi_up", "profile:next")
        self.pump(lambda: self.mouse.mode == p.DRIVER_MODE)
        self.listener.start.assert_called_once()
        self.app.set_action("dpi_up", "default")
        self.pump(lambda: self.mouse.mode == p.NORMAL_MODE)
        self.listener.stop.assert_called()

    def test_record_keys(self):
        with mock.patch.object(gui.RecordKeysDialog, "run", return_value="ctrl+shift+t"):
            self.app.record_keys("front")
        self.assertEqual(self.app.prof["buttons"]["front"], "keys:ctrl+shift+t")
        self.assertEqual(self.app.action_buttons["front"].cget("text"), "Ctrl+Shift+T")
        with mock.patch.object(gui.RecordKeysDialog, "run", return_value=None):
            self.app.record_keys("front")  # cancelled: nothing changes
        self.assertEqual(self.app.prof["buttons"]["front"], "keys:ctrl+shift+t")

    def test_run_a_program(self):
        with mock.patch.object(gui.filedialog, "askopenfilename", return_value="C:/Tools/backup.bat"):
            self.app.choose_program("rear")
        self.assertEqual(self.app.prof["buttons"]["rear"], r"run:C:\Tools\backup.bat")
        self.assertEqual(self.app.action_buttons["rear"].cget("text"), "Run: backup.bat")
        with mock.patch.object(gui.filedialog, "askopenfilename", return_value=""):
            self.app.choose_program("rear")  # cancelled: nothing changes
        self.assertEqual(self.app.prof["buttons"]["rear"], r"run:C:\Tools\backup.bat")

    def test_only_one_part_is_green(self):
        self.app.show()
        with mock.patch.object(self.app.view, "set_highlight") as highlight:
            self.app._select("rear")
            highlight.assert_called_with("rear")
            self.app._set_hover("dpi_up")
            highlight.assert_called_with("dpi_up")  # hover wins; never two at once
            self.app._set_hover(None)
            highlight.assert_called_with("rear")

    def test_sniper_dpi_is_checked(self):
        self.app.sniper_var.set(50)
        self.app._save_sniper()
        self.assertEqual(self.app.prof["sniper_dpi"], 400)
        self.app.sniper_var.set(600)
        self.app._save_sniper()
        self.assertEqual(self.app.prof["sniper_dpi"], 600)

    def test_dpi_actions_from_the_mouse(self):
        self.app._handle_dpi_action("up", True)
        self.assertEqual(self.mouse.active, 3)
        self.app._handle_dpi_action("cycle", True)
        self.app._handle_dpi_action("down", True)
        self.assertEqual(self.mouse.active, 3)
        self.idle()
        self.assertEqual(self.app.active_stage.get(), 3)
        self.app._handle_dpi_action("sniper", True)
        self.assertEqual(self.mouse.dpi_now, (400, 400))
        self.app._handle_dpi_action("sniper", False)
        self.assertEqual(self.mouse.dpi_now, (1600, 1600))


class Dpi(_App):
    def test_form_is_checked(self):
        self.app.stage_dpi[0].set(50)
        with self.assertRaisesRegex(ValueError, "Stage 1"):
            self.app.read_dpi_form()
        for used in self.app.stage_used:
            used.set(False)
        with self.assertRaisesRegex(ValueError, "at least one"):
            self.app.read_dpi_form()

    def test_active_stage_follows_turned_off_stages(self):
        self.app.stage_used[0].set(False)
        self.assertEqual(self.app.read_dpi_form(), ([800, 1600, 2400, 3200], 1, 1000))

    def test_edit_is_saved_to_the_mouse_by_itself(self):
        self.app.stage_dpi[4].set(4000)
        self.pump(lambda: "set_dpi_stages" in self.mouse.names(), seconds=2)
        self.assertEqual(self.mouse.stages[-1], (4000, 4000))
        self.assertEqual(config.load()["profiles"]["Default"]["dpi"]["stages"][-1], 4000)


class Lighting(_App):
    def test_apply_lighting(self):
        self.app.zone_vars["logo"]["effect"].set("static")
        self.app.zone_vars["logo"]["color"][:] = [1, 2, 3]
        self.app.apply_lighting()
        self.pump(lambda: "set_effect" in self.mouse.names())
        self.assertIn(("set_effect", (p.LOGO_LED, "static", (1, 2, 3))), self.mouse.calls)
        self.assertEqual(self.app.prof["lighting"]["logo"]["color"], [1, 2, 3])

    def test_colour_box_only_for_effects_with_a_colour(self):
        self.app.zone_vars["wheel"]["effect"].set("spectrum")
        with mock.patch.object(gui.colorchooser, "askcolor") as ask:
            self.app.pick_color("wheel")
            ask.assert_not_called()


class Profiles(_App):
    def test_new_profile_applies_factory_settings(self):
        with mock.patch.object(gui.NameDialog, "run", return_value="Gaming"):
            self.app.new_profile()
        self.assertEqual(self.app.cfg["active_profile"], "Gaming")
        self.pump(lambda: "set_dpi_stages" in self.mouse.names())
        self.assertEqual(self.mouse.stages, [(d, d) for d in (400, 800, 1600, 3200, 6400)])

    def test_duplicate_rename_switch_delete(self):
        self.app.set_action("rear", "keys:a")
        with mock.patch.object(gui.NameDialog, "run", return_value="Copy"):
            self.app.duplicate_profile()
        self.assertEqual(self.app.prof["buttons"]["rear"], "keys:a")
        with mock.patch.object(gui.NameDialog, "run", return_value="Work"):
            self.app.rename_profile()
        self.assertEqual(list(self.app.cfg["profiles"]), ["Default", "Work"])
        self.app._step_profile(1)
        self.assertEqual(self.app.cfg["active_profile"], "Default")
        self.app.switch_profile("Work")
        self.app.delete_profile()
        self.assertEqual(list(self.app.cfg["profiles"]), ["Default"])
        self.app.delete_profile()  # the last profile stays
        self.assertEqual(list(self.app.cfg["profiles"]), ["Default"])


class Reset(_App):
    def test_reset_buttons(self):
        self.app.set_action("rear", "keys:a")
        self.app.reset_buttons()
        self.assertEqual(set(self.app.prof["buttons"].values()), {"default"})

    def test_emergency_shortcut(self):
        self.app.set_action("left", "mouse:right")
        self.app.set_action("dpi_up", "profile:next")
        self.app._ui_queue.put(("emergency",))
        self.idle()
        self.assertEqual(set(self.app.prof["buttons"].values()), {"default"})
        self.assertEqual(config.load()["profiles"]["Default"]["buttons"]["left"], "default")
        self.app.tray.notify.assert_called_once()

    def test_reset_dpi_and_lighting(self):
        self.app.reset_dpi()
        self.app.reset_lighting()
        self.pump(lambda: "set_effect" in self.mouse.names())
        self.assertEqual(self.mouse.stages[-1], (6400, 6400))
        self.assertIn(("set_effect", (p.LOGO_LED, "spectrum", (68, 214, 44))), self.mouse.calls)

    def test_reset_everything(self):
        self.app.cfg["profiles"]["Other"] = config.default_profile()
        self.app.set_action("rear", "keys:a")
        self.yes = False
        self.app.reset_everything()
        self.assertIn("Other", self.app.cfg["profiles"])
        self.yes = True
        self.app.reset_everything()
        self.assertEqual(self.app.cfg, config.factory_settings())
        config.set_autostart.assert_called_with(False)
        self.assertEqual(config.load(), config.factory_settings())
        self.assertEqual(self.app.action_buttons["rear"].cget("text"), "Default (back)")


class Window(_App):
    def test_tray_tip_once_and_picture_freed(self):
        self.app.show()
        self.assertIsNotNone(self.app.view)
        self.app.on_close()
        self.app.on_close()
        self.app.tray.notify.assert_called_once()
        self.assertIsNone(self.app.view)

    def test_quit_gives_dpi_buttons_back(self):
        self.app.set_action("profile", "profile:next")
        self.pump(lambda: self.mouse.mode == p.DRIVER_MODE)
        with mock.patch.object(self.app.root, "destroy"):
            self.app.quit()
        self.assertEqual(self.mouse.mode, p.NORMAL_MODE)
        self.assertTrue(self.mouse.closed)


class Tray(_App):
    def test_tray_menu_lists_the_profiles(self):
        self.app.cfg["profiles"]["Gaming"] = config.default_profile()
        with mock.patch.object(gui, "Tray") as tray_class:
            self.real_start_tray(self.app)
        _tooltip, _icon, on_click, menu = tray_class.call_args.args
        tray_class.return_value.start.assert_called_once()
        items = menu()
        self.assertEqual(items[0].text, "Open OpenAdder")
        profiles = items[1].action
        self.assertEqual([i.text for i in profiles], ["Default", "Gaming"])
        self.assertEqual([i.checked for i in profiles], [True, False])
        profiles[1].action()  # click "Gaming"
        self.idle()
        self.assertEqual(self.app.cfg["active_profile"], "Gaming")
        on_click()
        self.idle()
        self.assertTrue(self.app._visible)


class Dialogs(_App):
    def key(self, keysym):
        return mock.Mock(keysym=keysym)

    def test_record_keys_dialog(self):
        dlg = RecordKeysDialog(self.app.root, "Rear side button")
        self.addCleanup(lambda: dlg.winfo_exists() and dlg.destroy())
        for keysym in ("Control_L", "Shift_L"):
            dlg._press(self.key(keysym))
        self.assertTrue(dlg.ok.instate(["disabled"]))  # modifiers alone are not enough
        dlg._press(self.key("T"))
        self.assertEqual(dlg.display.cget("text"), "Ctrl+Shift+T")
        for keysym in ("T", "Shift_L", "Control_L"):
            dlg._release(self.key(keysym))
        dlg._press(self.key("XF86AudioMute"))
        self.assertIn("cannot send", dlg.note.cget("text"))
        dlg.accept()
        self.assertEqual(dlg.result, "ctrl+shift+t")

    def test_name_dialog(self):
        dlg = NameDialog(self.app.root, "New", "Name:", check=lambda n: "taken" if n == "A" else None)
        dlg.var.set("A")
        dlg.accept()
        self.assertEqual(dlg.error.cget("text"), "taken")
        dlg.var.set("  B ")
        dlg.accept()
        self.assertEqual(dlg.result, "B")


if __name__ == "__main__":
    unittest.main()
