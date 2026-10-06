"""Razer HID control protocol for the supported mice (see models.py).

All command bytes come from the public OpenRazer project
(driver/razerchromacommon.c, driver/razermouse_driver.c) and from
gpoulios/deathadderv2 (DPI stages, tested on the DeathAdder V2).

A report is 90 bytes:
    0      status          (0x00 new, 0x02 OK, 0x01 busy, 0x03 fail, 0x04 timeout, 0x05 unsupported)
    1      transaction id  (depends on the model: the device fills it in, see with_transaction_id)
    2-3    remaining packets (big endian, always 0 here)
    4      protocol type   (always 0)
    5      data size       (number of argument bytes used)
    6      command class
    7      command id      (bit 7 set = "get")
    8-87   arguments
    88     CRC             (XOR of bytes 2..87)
    89     reserved
"""

from dataclasses import dataclass

REPORT_LEN = 90

NOSTORE = 0x00
VARSTORE = 0x01

SCROLL_WHEEL_LED = 0x01
LOGO_LED = 0x04
LEDS = {"logo": LOGO_LED, "wheel": SCROLL_WHEEL_LED}

STATUS_NAMES = {
    0x00: "new",
    0x01: "busy",
    0x02: "ok",
    0x03: "failure",
    0x04: "timeout",
    0x05: "not supported",
}

MIN_DPI = 100
MAX_DPI = 30000    # highest of all models; each model has its own limit
MAX_DPI_STAGES = 5

POLL_RATE_TO_BYTE = {1000: 0x01, 500: 0x02, 125: 0x08}
BYTE_TO_POLL_RATE = {v: k for k, v in POLL_RATE_TO_BYTE.items()}


def crc(report: bytes) -> int:
    value = 0
    for b in report[2:88]:
        value ^= b
    return value


def build(command_class: int, command_id: int, data_size: int, args: bytes = b"") -> bytes:
    if len(args) > 80:
        raise ValueError("arguments longer than 80 bytes")
    r = bytearray(REPORT_LEN)
    r[5] = data_size
    r[6] = command_class
    r[7] = command_id
    r[8:8 + len(args)] = args
    r[88] = crc(r)
    return bytes(r)


def with_transaction_id(request: bytes, tid: int) -> bytes:
    """The request for a model with this transaction id. Byte 1 is not part of the CRC."""
    return request[:1] + bytes((tid,)) + request[2:]


@dataclass
class Response:
    status: int
    command_class: int
    command_id: int
    args: bytes

    @property
    def ok(self) -> bool:
        return self.status == 0x02

    @property
    def status_name(self) -> str:
        return STATUS_NAMES.get(self.status, f"unknown 0x{self.status:02x}")


def parse(raw: bytes) -> Response:
    if len(raw) != REPORT_LEN:
        raise ValueError(f"expected {REPORT_LEN} bytes, got {len(raw)}")
    return Response(raw[0], raw[6], raw[7], bytes(raw[8:88]))


def _clamp_dpi(dpi: int) -> int:
    return max(MIN_DPI, min(MAX_DPI, int(dpi)))


def _rgb(color) -> bytes:
    r, g, b = color
    return bytes((r & 0xFF, g & 0xFF, b & 0xFF))


# --- Standard -------------------------------------------------------------

def get_firmware() -> bytes:
    return build(0x00, 0x81, 0x02)


# --- Polling rate ---------------------------------------------------------

def set_poll_rate(hz: int) -> bytes:
    if hz not in POLL_RATE_TO_BYTE:
        raise ValueError(f"polling rate must be one of {sorted(POLL_RATE_TO_BYTE)}")
    return build(0x00, 0x05, 0x01, bytes((POLL_RATE_TO_BYTE[hz],)))


def get_poll_rate() -> bytes:
    return build(0x00, 0x85, 0x01)


def parse_poll_rate(resp: Response) -> int:
    return BYTE_TO_POLL_RATE.get(resp.args[0], 0)


# The DeathAdder V3 and newer mice use another command, for up to 8000 Hz.
POLL_RATE_V2_TO_BYTE = {8000: 0x01, 4000: 0x02, 2000: 0x04, 1000: 0x08, 500: 0x10, 125: 0x40}
BYTE_TO_POLL_RATE_V2 = {v: k for k, v in POLL_RATE_V2_TO_BYTE.items()}


def set_poll_rate_v2(hz: int, argument: int) -> bytes:
    """Razer sends this twice, with argument 0x00 and then 0x01."""
    if hz not in POLL_RATE_V2_TO_BYTE:
        raise ValueError(f"polling rate must be one of {sorted(POLL_RATE_V2_TO_BYTE)}")
    return build(0x00, 0x40, 0x02, bytes((argument, POLL_RATE_V2_TO_BYTE[hz])))


def get_poll_rate_v2() -> bytes:
    return build(0x00, 0xC0, 0x01)


def parse_poll_rate_v2(resp: Response) -> int:
    return BYTE_TO_POLL_RATE_V2.get(resp.args[1], 0)


# --- DPI ------------------------------------------------------------------

def set_dpi(dpi_x: int, dpi_y: int) -> bytes:
    x, y = _clamp_dpi(dpi_x), _clamp_dpi(dpi_y)
    return build(0x04, 0x05, 0x07, bytes((VARSTORE, x >> 8, x & 0xFF, y >> 8, y & 0xFF, 0, 0)))


def get_dpi() -> bytes:
    return build(0x04, 0x85, 0x07, bytes((NOSTORE,)))


def parse_dpi(resp: Response) -> tuple:
    a = resp.args
    return (a[1] << 8) | a[2], (a[3] << 8) | a[4]


def set_dpi_stages(stages, active: int) -> bytes:
    """stages: list of (dpi_x, dpi_y). active: 1-based index of the active stage."""
    if not 1 <= len(stages) <= MAX_DPI_STAGES:
        raise ValueError(f"need 1 to {MAX_DPI_STAGES} DPI stages")
    if not 1 <= active <= len(stages):
        raise ValueError("active stage out of range")
    args = bytearray((NOSTORE, active, len(stages)))
    for i, (dx, dy) in enumerate(stages, start=1):
        x, y = _clamp_dpi(dx), _clamp_dpi(dy)
        args += bytes((i, x >> 8, x & 0xFF, y >> 8, y & 0xFF, 0, 0))
    return build(0x04, 0x06, len(args), bytes(args))


def get_dpi_stages() -> bytes:
    return build(0x04, 0x86, 0x26, bytes((NOSTORE,)))


def parse_dpi_stages(resp: Response) -> tuple:
    """Returns (stages, active) with active 1-based."""
    a = resp.args
    active, count = a[1], a[2]
    stages = []
    for i in range(min(count, MAX_DPI_STAGES)):
        o = 3 + i * 7
        stages.append(((a[o + 1] << 8) | a[o + 2], (a[o + 3] << 8) | a[o + 4]))
    return stages, active


# --- Lighting (extended matrix, class 0x0F) -------------------------------

def _effect(arg_size: int, led: int, effect_id: int) -> bytearray:
    args = bytearray(arg_size)
    args[0] = VARSTORE
    args[1] = led
    args[2] = effect_id
    return args


def effect_off(led: int) -> bytes:
    return build(0x0F, 0x02, 0x06, bytes(_effect(0x06, led, 0x00)))


def effect_static(led: int, color) -> bytes:
    args = _effect(0x09, led, 0x01)
    args[5] = 0x01
    args[6:9] = _rgb(color)
    return build(0x0F, 0x02, 0x09, bytes(args))


def effect_breathing(led: int, color) -> bytes:
    args = _effect(0x09, led, 0x02)
    args[3] = 0x01
    args[5] = 0x01
    args[6:9] = _rgb(color)
    return build(0x0F, 0x02, 0x09, bytes(args))


def effect_spectrum(led: int) -> bytes:
    return build(0x0F, 0x02, 0x06, bytes(_effect(0x06, led, 0x03)))


def effect_reactive(led: int, color, speed: int = 2) -> bytes:
    args = _effect(0x09, led, 0x05)
    args[4] = max(1, min(4, speed))
    args[5] = 0x01
    args[6:9] = _rgb(color)
    return build(0x0F, 0x02, 0x09, bytes(args))


def set_brightness(led: int, value: int) -> bytes:
    return build(0x0F, 0x04, 0x03, bytes((VARSTORE, led, max(0, min(255, value)))))


def get_brightness(led: int) -> bytes:
    return build(0x0F, 0x84, 0x03, bytes((VARSTORE, led)))


def parse_brightness(resp: Response) -> int:
    return resp.args[2]


# --- Device mode ----------------------------------------------------------
# Normal mode (0x00): the firmware handles the DPI and profile buttons.
# Driver mode (0x03): the DPI and profile buttons report to the PC instead
# ("report 4" on interface 1: 0x20 DPI up, 0x21 DPI down, 0x50 profile).

NORMAL_MODE = 0x00
DRIVER_MODE = 0x03

REPORT4_CODES = {0x20: "dpi_up", 0x21: "dpi_down", 0x50: "profile"}


def set_device_mode(mode: int) -> bytes:
    if mode not in (NORMAL_MODE, DRIVER_MODE):
        raise ValueError("device mode must be 0x00 or 0x03")
    return build(0x00, 0x04, 0x02, bytes((mode, 0x00)))


def get_device_mode() -> bytes:
    return build(0x00, 0x84, 0x02)


def parse_report4(data: bytes) -> set:
    """Buttons held in a 'report 4' input report, or None for other reports."""
    if not data or data[0] != 0x04:
        return None
    return {REPORT4_CODES[c] for c in data[1:16] if c in REPORT4_CODES}
