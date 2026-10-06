"""The Razer mice that OpenAdder supports, and what each one can do.

The data comes from OpenRazer (driver/razermouse_driver.c and
daemon/openrazer_daemon/hardware/mouse.py). Only the DeathAdder V2 is tested on a
real mouse. The other models use the same commands with other values; "tested" is
set when an owner confirms that a model works.
"""

from dataclasses import dataclass

BASIC_BUTTONS = ("left", "right", "middle", "wheel_up", "wheel_down", "front", "rear")
DPI_BUTTONS = ("dpi_up", "dpi_down")
ALL_EFFECTS = ("static", "breathing", "spectrum", "reactive", "off")
SIMPLE_EFFECTS = ("static", "breathing", "off")


@dataclass(frozen=True)
class Model:
    pid: int                        # USB product id (the vendor id is always 0x1532)
    name: str
    tid: int                        # transaction id for most commands
    max_dpi: int
    leds: tuple = ("logo", "wheel")
    effects: tuple = ALL_EFFECTS
    led_tid: int = None             # transaction id for lighting, if it is different
    stages: bool = True             # the mouse stores DPI stages
    stage_tid: int = None           # transaction id for DPI stages, if it is different
    poll_rates: tuple = (125, 500, 1000)
    hyperpolling: bool = False      # uses the newer polling-rate command (up to 8000 Hz)
    buttons: tuple = BASIC_BUTTONS
    picture: bool = True            # the DeathAdder picture fits this mouse
    tested: bool = False

    @property
    def usb_id(self) -> str:
        return f"1532:{self.pid:04x}"


MODELS = (
    Model(0x0084, "DeathAdder V2", 0x3F, 20000, buttons=BASIC_BUTTONS + DPI_BUTTONS + ("profile",),
          tested=True),
    Model(0x008C, "DeathAdder V2 Mini", 0x3F, 8500, leds=("logo",), stage_tid=0xFF),
    Model(0x00A1, "DeathAdder V2 Lite", 0x1F, 8500, leds=("logo",), stage_tid=0xFF),
    Model(0x005C, "DeathAdder Elite", 0x3F, 16000, stages=False, buttons=BASIC_BUTTONS + DPI_BUTTONS),
    Model(0x006E, "DeathAdder Essential", 0xFF, 6400, effects=SIMPLE_EFFECTS, led_tid=0x3F,
          stages=False),
    Model(0x0071, "DeathAdder Essential (White Edition)", 0xFF, 6400, effects=SIMPLE_EFFECTS,
          led_tid=0x3F, stages=False),
    Model(0x0098, "DeathAdder Essential (2021)", 0xFF, 6400, leds=("logo",), effects=SIMPLE_EFFECTS,
          led_tid=0x3F, stages=False),
    Model(0x00B2, "DeathAdder V3", 0x1F, 30000, leds=(),
          poll_rates=(125, 500, 1000, 2000, 4000, 8000), hyperpolling=True),
    Model(0x00A3, "Cobra", 0xFF, 8500, leds=("logo",), led_tid=0x1F, picture=False),
)

BY_PID = {m.pid: m for m in MODELS}
DEFAULT = MODELS[0]
HIGHEST_DPI = max(m.max_dpi for m in MODELS)
