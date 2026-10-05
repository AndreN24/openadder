import sys
import unittest
from unittest import mock

from openadder import config

from .helpers import TempConfig


class Settings(unittest.TestCase):
    def setUp(self):
        self.tmp = TempConfig().start()

    def tearDown(self):
        self.tmp.stop()

    def test_first_start_is_factory_settings(self):
        self.assertEqual(config.load(), config.factory_settings())
        prof = config.load()["profiles"]["Default"]
        self.assertEqual(len(prof["buttons"]), 10)
        self.assertEqual(prof["dpi"]["stages"], [400, 800, 1600, 3200, 6400])

    def test_save_and_load_round_trip(self):
        cfg = config.load()
        cfg["profiles"]["Gaming"] = config.default_profile()
        cfg["profiles"]["Gaming"]["buttons"]["dpi_up"] = "profile:next"
        cfg["active_profile"] = "Gaming"
        cfg["tray_tip_shown"] = True
        config.save(cfg)
        again = config.load()
        self.assertEqual(again["active_profile"], "Gaming")
        self.assertEqual(again["profiles"]["Gaming"]["buttons"]["dpi_up"], "profile:next")
        self.assertTrue(again["tray_tip_shown"])

    def test_missing_values_come_from_the_factory_profile(self):
        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config.CONFIG_FILE.write_text('{"active_profile": "Gone", "profiles": {"A": '
                                      '{"buttons": {"rear": "keys:a"}, "lighting": {"logo": '
                                      '{"brightness": 5}}}}}')
        cfg = config.load()
        self.assertEqual(cfg["active_profile"], "A")
        prof = cfg["profiles"]["A"]
        self.assertEqual(prof["buttons"]["rear"], "keys:a")
        self.assertEqual(prof["buttons"]["left"], "default")
        self.assertEqual(prof["lighting"]["logo"], {"effect": "spectrum", "color": [68, 214, 44],
                                                    "brightness": 5})

    def test_broken_file_gives_factory_settings(self):
        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config.CONFIG_FILE.write_text("{not json")
        self.assertEqual(config.load(), config.factory_settings())


class Autostart(unittest.TestCase):
    def test_launch_command(self):
        self.assertTrue(config._launch_command().endswith('OpenAdder.pyw" --minimized'))
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "executable", r"C:\x\OpenAdder.exe"):
            self.assertEqual(config._launch_command(), r'"C:\x\OpenAdder.exe" --minimized')

    def test_refresh_only_rewrites_an_outdated_entry(self):
        with mock.patch.object(config, "set_autostart") as set_autostart:
            with mock.patch.object(config, "_read_autostart", return_value=None):
                config.refresh_autostart()
            with mock.patch.object(config, "_read_autostart", return_value=config._launch_command()):
                config.refresh_autostart()
            set_autostart.assert_not_called()
            with mock.patch.object(config, "_read_autostart", return_value='"old.exe" --minimized'):
                config.refresh_autostart()
            set_autostart.assert_called_once_with(True)


class FakeRegistry:
    """Stands in for winreg, so the tests never touch the real autostart entry."""

    HKEY_CURRENT_USER, KEY_SET_VALUE, REG_SZ = object(), 2, 1

    def __init__(self):
        self.values = {}

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def OpenKey(self, *args):
        return self._Key()

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], self.REG_SZ

    def SetValueEx(self, key, name, _reserved, _type, value):
        self.values[name] = value

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


class Registry(unittest.TestCase):
    def test_turn_autostart_on_and_off(self):
        reg = FakeRegistry()
        with mock.patch.object(config, "winreg", reg):
            self.assertFalse(config.autostart_enabled())
            config.set_autostart(True)
            self.assertTrue(config.autostart_enabled())
            self.assertEqual(reg.values["OpenAdder"], config._launch_command())
            config.set_autostart(False)
            config.set_autostart(False)  # turning it off twice is fine
            self.assertFalse(config.autostart_enabled())


if __name__ == "__main__":
    unittest.main()
