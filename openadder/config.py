"""Settings file (%APPDATA%\\OpenAdder\\config.json) and the Windows autostart entry."""

import json
import os
import sys
import winreg
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "OpenAdder"
CONFIG_FILE = CONFIG_DIR / "config.json"

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "OpenAdder"

BUTTON_KEYS = ("left", "right", "middle", "wheel_up", "wheel_down", "front", "rear",
               "dpi_up", "dpi_down", "profile")
DEFAULT_PROFILE_NAME = "Default"


def default_profile() -> dict:
    """Factory values for every setting."""
    zone = {"effect": "spectrum", "color": [68, 214, 44], "brightness": 255}
    return {
        "buttons": {b: "default" for b in BUTTON_KEYS},
        "sniper_dpi": 400,
        "dpi": {"stages": [400, 800, 1600, 3200, 6400], "active": 2},
        "poll": 1000,
        "lighting": {"logo": dict(zone), "wheel": dict(zone)},
    }


def _fill_profile(saved: dict) -> dict:
    """A complete profile: saved values on top of the factory values."""
    prof = default_profile()
    for key, value in saved.items():
        if key == "lighting" and isinstance(value, dict):
            for zone, zcfg in value.items():
                if zone in prof["lighting"] and isinstance(zcfg, dict):
                    prof["lighting"][zone].update(zcfg)
        elif isinstance(value, dict) and isinstance(prof.get(key), dict):
            prof[key].update(value)
        else:
            prof[key] = value
    return prof


def factory_settings() -> dict:
    """All settings as on a first start: one "Default" profile with the factory values."""
    return {"active_profile": DEFAULT_PROFILE_NAME,
            "profiles": {DEFAULT_PROFILE_NAME: default_profile()},
            "tray_tip_shown": False}


def load() -> dict:
    """Returns {"active_profile": name, "profiles": {name: profile}, "tray_tip_shown": bool}."""
    try:
        saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    profiles = {name: _fill_profile(p) for name, p in saved.get("profiles", {}).items()}
    if not profiles:
        return factory_settings()
    active = saved.get("active_profile")
    if active not in profiles:
        active = next(iter(profiles))
    return {"active_profile": active, "profiles": profiles,
            "tray_tip_shown": bool(saved.get("tray_tip_shown"))}


def save(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_FILE)


def _launch_command() -> str:
    if getattr(sys, "frozen", False):  # built with PyInstaller: OpenAdder.exe
        return f'"{sys.executable}" --minimized'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw
    script = Path(__file__).resolve().parent.parent / "OpenAdder.pyw"
    return f'"{exe}" "{script}" --minimized'


def _read_autostart():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, RUN_VALUE)[0]
    except OSError:
        return None


def autostart_enabled() -> bool:
    return _read_autostart() is not None


def set_autostart(enabled: bool):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


def refresh_autostart():
    """If autostart is on, point it at this copy of OpenAdder (for example after a move)."""
    current = _read_autostart()
    if current is not None and current != _launch_command():
        set_autostart(True)
