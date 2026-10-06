"""Shared test helpers: a temporary settings folder and a simulated mouse."""

import tempfile
from pathlib import Path

from openadder import config, models


class TempConfig:
    """Points the settings file at a temporary folder for the duration of a test."""

    def start(self):
        self._old = (config.CONFIG_DIR, config.CONFIG_FILE)
        self._tmp = tempfile.TemporaryDirectory()
        config.CONFIG_DIR = Path(self._tmp.name)
        config.CONFIG_FILE = config.CONFIG_DIR / "config.json"
        return self

    def stop(self):
        config.CONFIG_DIR, config.CONFIG_FILE = self._old
        self._tmp.cleanup()


class FakeMouse:
    """Behaves like device.RazerMouse and records every call."""

    def __init__(self, stages=(400, 800, 1600, 2400, 3200), active=2, poll=1000, brightness=168,
                 model=models.DEFAULT):
        self.model = model
        self.stages = [(d, d) for d in stages]
        self.active = active
        self.poll = poll
        self.bright = {1: brightness, 4: brightness}
        self.mode = 0
        self.dpi_now = self.stages[active - 1]
        self.calls = []
        self.closed = False

    def _log(self, name, *args):
        self.calls.append((name, args))

    def names(self):
        return [c[0] for c in self.calls]

    def firmware(self):
        return "1.02"

    def poll_rate(self):
        return self.poll

    def brightness(self, led):
        return self.bright[led]

    def dpi_stages(self):
        assert self.model.stages, "this model stores no DPI stages"
        return list(self.stages), self.active

    def dpi(self):
        return self.dpi_now

    def device_mode(self):
        return self.mode

    def set_device_mode(self, mode):
        self._log("set_device_mode", mode)
        self.mode = mode

    def set_dpi_stages(self, stages, active):
        if self.model.stages:
            self._log("set_dpi_stages", list(stages), active)
            self.stages, self.active = list(stages), active

    def set_dpi(self, x, y=None):
        self._log("set_dpi", x)
        self.dpi_now = (x, x if y is None else y)

    def set_poll_rate(self, hz):
        self._log("set_poll_rate", hz)
        self.poll = hz

    def set_effect(self, led, effect, color=(0, 255, 0)):
        self._log("set_effect", led, effect, tuple(color))

    def set_brightness(self, led, value):
        self._log("set_brightness", led, value)
        self.bright[led] = value

    def close(self):
        self.closed = True
