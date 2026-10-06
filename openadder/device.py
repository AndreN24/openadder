"""USB transport: talks to the mouse through the standard Windows HID driver."""

import sys
import threading
import time

import hid

from . import __version__, models
from . import protocol as p

VENDOR_ID = 0x1532


class DeviceError(Exception):
    pass


class RazerMouse:
    def __init__(self, handle, model: models.Model = models.DEFAULT):
        self._h = handle
        self.model = model
        self._lock = threading.Lock()

    @classmethod
    def open(cls) -> "RazerMouse":
        """Find a supported mouse, take its control interface (interface 0) and check that it answers."""
        candidates = [d for d in hid.enumerate(VENDOR_ID, 0) if d["product_id"] in models.BY_PID]
        if not candidates:
            raise DeviceError("No supported Razer mouse found. Is it plugged in?")
        candidates.sort(key=lambda d: d["interface_number"] != 0)
        for info in candidates:
            h = hid.device()
            try:
                h.open_path(info["path"])
            except OSError:
                continue
            dev = cls(h, models.BY_PID[info["product_id"]])
            try:
                if dev._transact(p.get_firmware()).ok:
                    return dev
            except (OSError, ValueError, DeviceError):
                pass
            h.close()
        raise DeviceError("The mouse was found, but its control interface did not answer.")

    def close(self):
        self._h.close()

    def _transact(self, request: bytes, tid: int = None, retries: int = 10) -> p.Response:
        request = p.with_transaction_id(request, tid or self.model.tid)
        with self._lock:
            self._h.send_feature_report(b"\x00" + request)
            for _ in range(retries):
                time.sleep(0.005)
                raw = bytes(self._h.get_feature_report(0x00, p.REPORT_LEN + 1))
                # hidapi on Windows puts the report id (0x00) first.
                if len(raw) == p.REPORT_LEN + 1:
                    raw = raw[1:]
                resp = p.parse(raw)
                if resp.status != 0x01:  # not busy
                    break
        if resp.command_class != request[6] or resp.command_id != request[7]:
            raise DeviceError("The mouse answered a different command.")
        return resp

    def _run(self, request: bytes, tid: int = None) -> p.Response:
        resp = self._transact(request, tid)
        if not resp.ok:
            raise DeviceError(
                f"Command 0x{request[6]:02x}/0x{request[7]:02x} failed: {resp.status_name}")
        return resp

    def _clamp(self, dpi: int) -> int:
        return min(int(dpi), self.model.max_dpi)

    # --- Read ---------------------------------------------------------------

    def firmware(self) -> str:
        a = self._run(p.get_firmware()).args
        return f"{a[0]}.{a[1]:02d}"

    def dpi(self) -> tuple:
        return p.parse_dpi(self._run(p.get_dpi()))

    def dpi_stages(self) -> tuple:
        """(stages, active). Only for models that store stages (model.stages)."""
        return p.parse_dpi_stages(self._run(p.get_dpi_stages(), self.model.stage_tid))

    def poll_rate(self) -> int:
        if self.model.hyperpolling:
            return p.parse_poll_rate_v2(self._run(p.get_poll_rate_v2()))
        return p.parse_poll_rate(self._run(p.get_poll_rate()))

    def brightness(self, led: int) -> int:
        return p.parse_brightness(self._run(p.get_brightness(led), self.model.led_tid))

    # --- Write --------------------------------------------------------------

    def set_dpi(self, dpi_x: int, dpi_y: int = None):
        x = self._clamp(dpi_x)
        self._run(p.set_dpi(x, x if dpi_y is None else self._clamp(dpi_y)))

    def set_dpi_stages(self, stages, active: int):
        """Does nothing on models without stage memory: OpenAdder keeps their stages."""
        if self.model.stages:
            stages = [(self._clamp(x), self._clamp(y)) for x, y in stages]
            self._run(p.set_dpi_stages(stages, active), self.model.stage_tid)

    def set_poll_rate(self, hz: int):
        if self.model.hyperpolling:
            for argument in (0x00, 0x01):
                self._run(p.set_poll_rate_v2(hz, argument))
        else:
            self._run(p.set_poll_rate(hz))

    def set_brightness(self, led: int, value: int):
        self._run(p.set_brightness(led, value), self.model.led_tid)

    def device_mode(self) -> int:
        return self._run(p.get_device_mode()).args[0]

    def set_device_mode(self, mode: int):
        self._run(p.set_device_mode(mode))

    def set_effect(self, led: int, effect: str, color=(0, 255, 0)):
        builders = {
            "off": lambda: p.effect_off(led),
            "static": lambda: p.effect_static(led, color),
            "breathing": lambda: p.effect_breathing(led, color),
            "spectrum": lambda: p.effect_spectrum(led),
            "reactive": lambda: p.effect_reactive(led, color),
        }
        if effect not in builders:
            raise ValueError(f"unknown effect {effect!r}")
        self._run(builders[effect](), self.model.led_tid)


def diagnostic_report(dev: RazerMouse = None) -> str:
    """Plain text for a bug report: the Razer devices that Windows sees and what the mouse answers."""
    win = sys.getwindowsversion()
    lines = [f"OpenAdder {__version__} on Windows {win.major}.{win.minor}.{win.build}"]
    interfaces = {}
    for info in hid.enumerate(VENDOR_ID, 0):
        interfaces.setdefault(info["product_id"], set()).add(info["interface_number"])
    seen = [f"1532:{pid:04x} (interfaces {', '.join(map(str, sorted(i)))})"
            for pid, i in sorted(interfaces.items())]
    lines.append(f"Razer USB devices: {', '.join(seen) or 'none'}")
    if dev is None:
        lines.append("Mouse: not connected")
        return "\n".join(lines)
    m = dev.model
    lines.append(f"Mouse: {m.name} ({m.usb_id}), {'tested' if m.tested else 'not tested yet'}")
    checks = [("firmware", dev.firmware), ("DPI", dev.dpi), ("polling rate", dev.poll_rate),
              ("device mode", dev.device_mode)]
    if m.stages:
        checks.append(("DPI stages", dev.dpi_stages))
    for name in m.leds:
        checks.append((f"{name} brightness", lambda led=p.LEDS[name]: dev.brightness(led)))
    for name, read in checks:
        try:
            value = read()
        except (DeviceError, OSError, ValueError) as exc:
            value = f"error: {exc}"
        lines.append(f"{name}: {value}")
    return "\n".join(lines)


class ButtonListener:
    """Reads the DPI and profile buttons while the mouse is in driver mode.

    on_event(button, pressed) runs on the listener thread.
    """

    def __init__(self, on_event):
        self._on_event = on_event
        self._stop = threading.Event()
        self._threads = []

    def start(self, pid: int):
        self.stop()
        self._stop.clear()
        for info in hid.enumerate(VENDOR_ID, pid):
            # "report 4" arrives on an interface-1 collection without a usage.
            if info["interface_number"] != 1 or info["usage_page"] != 0x01 or info["usage"] != 0x00:
                continue
            h = hid.device()
            try:
                h.open_path(info["path"])
            except OSError:
                continue
            t = threading.Thread(target=self._loop, args=(h,), daemon=True, name="dpi-buttons")
            t.start()
            self._threads.append(t)

    def stop(self):
        self._stop.set()
        for t in self._threads:
            t.join(1)
        self._threads = []

    def _loop(self, h):
        held = set()
        try:
            while not self._stop.is_set():
                try:
                    data = h.read(64, 200)
                except OSError:
                    return  # unplugged
                now = p.parse_report4(bytes(data)) if data else None
                if now is None:
                    continue
                for button in sorted(now - held):
                    self._on_event(button, True)
                for button in sorted(held - now):
                    self._on_event(button, False)
                held = now
        finally:
            for button in sorted(held):
                self._on_event(button, False)
            h.close()
