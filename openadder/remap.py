"""Software remap of the mouse buttons.

Two input paths feed one worker thread:

* A Windows low-level mouse hook for the buttons that Windows sees:
  left, right, middle (wheel click), wheel up, wheel down and the two side
  buttons. When a button has an action, the hook blocks the original event.
  The hook is installed only while at least one of these buttons is remapped.
  Clicks inside OpenAdder's own window are never changed, so a bad remap
  cannot lock you out.
* External events (press / release) for the DPI and profile buttons, which
  the mouse reports only in driver mode (see device.ButtonListener).

Action strings:
    "default"        normal behaviour of the button
    "disabled"       do nothing
    "keys:ctrl+c"    hold a key combination while the button is held
    "mouse:left"     hold a mouse button (left, right, middle, back, forward)
    "mouse:wheel_up" / "mouse:wheel_down"   one scroll step per press
    "dpi:up" / "dpi:down" / "dpi:cycle"     change the DPI stage
    "dpi:sniper"     use the sniper DPI while the button is held
    "profile:next" / "profile:prev"         switch the OpenAdder profile
    "run:<path>"     start a program, script or file (on press)
"""

import ctypes
import os
import queue
import threading
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_MOUSE_LL = 14
HC_ACTION = 0
WM_QUIT = 0x0012
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_MOUSEWHEEL = 0x020A
WM_XBUTTONDOWN, WM_XBUTTONUP = 0x020B, 0x020C
LLMHF_INJECTED = 0x01
XBUTTON1 = 1
XBUTTON2 = 2
WHEEL_DELTA = 120
GA_ROOT = 2

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP = 0x0080, 0x0100
MOUSEEVENTF_WHEEL = 0x0800

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t

# Buttons that the hook handles, and the buttons that come from driver mode.
HOOK_BUTTONS = ("left", "right", "middle", "wheel_up", "wheel_down", "front", "rear")
DRIVER_BUTTONS = ("dpi_up", "dpi_down", "profile")
ALL_BUTTONS = HOOK_BUTTONS + DRIVER_BUTTONS

# What "default" means for the driver-mode buttons (the firmware no longer
# handles them in driver mode, so OpenAdder does the same job).
DRIVER_DEFAULTS = {"dpi_up": "dpi:up", "dpi_down": "dpi:down", "profile": "disabled"}

_DOWN = {WM_LBUTTONDOWN: "left", WM_RBUTTONDOWN: "right", WM_MBUTTONDOWN: "middle"}
_UP = {WM_LBUTTONUP: "left", WM_RBUTTONUP: "right", WM_MBUTTONUP: "middle"}
_HOOK_MESSAGES = set(_DOWN) | set(_UP) | {WM_MOUSEWHEEL, WM_XBUTTONDOWN, WM_XBUTTONUP}


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

_OWN_PID = os.getpid()


# --- Key names -------------------------------------------------------------

MODIFIERS = {"ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B}

NAMED_KEYS = {
    "enter": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "home": 0x24,
    "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "up": 0x26, "down": 0x28,
    "left": 0x25, "right": 0x27, "printscreen": 0x2C, "capslock": 0x14,
    "minus": 0xBD, "equals": 0xBB, "comma": 0xBC, "period": 0xBE, "slash": 0xBF,
    "volume_up": 0xAF, "volume_down": 0xAE, "volume_mute": 0xAD,
    "play_pause": 0xB3, "next_track": 0xB0, "prev_track": 0xB1, "media_stop": 0xB2,
    "browser_back": 0xA6, "browser_forward": 0xA7,
}
NAMED_KEYS.update({chr(c): c - 32 for c in range(ord("a"), ord("z") + 1)})
NAMED_KEYS.update({str(d): 0x30 + d for d in range(10)})
NAMED_KEYS.update({f"f{n}": 0x6F + n for n in range(1, 25)})

EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2C, 0x2D, 0x2E, 0x5B,
                0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3, 0xA6, 0xA7}

MOUSE_FLAGS = {
    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP, 0),
    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP, 0),
    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP, 0),
    "back": (MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP, XBUTTON1),
    "forward": (MOUSEEVENTF_XDOWN, MOUSEEVENTF_XUP, XBUTTON2),
}
WHEEL_OUTPUTS = {"wheel_up": WHEEL_DELTA, "wheel_down": -WHEEL_DELTA}
DPI_ACTIONS = ("up", "down", "cycle", "sniper")
PROFILE_ACTIONS = ("next", "prev")


def parse_keys(text: str) -> list:
    """'ctrl+shift+t' -> [0x11, 0x10, 0x54]. Raises ValueError on unknown names."""
    vks = []
    for part in text.lower().replace(" ", "").split("+"):
        if not part:
            continue
        vk = MODIFIERS.get(part) or NAMED_KEYS.get(part)
        if vk is None:
            raise ValueError(f"unknown key name: {part!r}")
        vks.append(vk)
    if not vks:
        raise ValueError("no keys given")
    return vks


def validate_action(action: str):
    """Raises ValueError if the action string is not valid."""
    if action in ("default", "disabled"):
        return
    kind, _, arg = action.partition(":")
    if kind == "keys":
        parse_keys(arg)
    elif kind == "mouse":
        if arg not in MOUSE_FLAGS and arg not in WHEEL_OUTPUTS:
            raise ValueError(f"unknown mouse button: {arg!r}")
    elif kind == "dpi":
        if arg not in DPI_ACTIONS:
            raise ValueError(f"unknown DPI action: {arg!r}")
    elif kind == "profile":
        if arg not in PROFILE_ACTIONS:
            raise ValueError(f"unknown profile action: {arg!r}")
    elif kind == "run":
        if not arg.strip():
            raise ValueError("no program given")
    else:
        raise ValueError(f"unknown action: {action!r}")


# --- Output ----------------------------------------------------------------

def _send(inputs):
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _key_input(vk: int, up: bool) -> INPUT:
    flags = KEYEVENTF_KEYUP if up else 0
    if vk in EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY
    scan = user32.MapVirtualKeyW(vk, 0)
    return INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(vk, scan, flags, 0, 0)))


def send_keys(vks: list, up: bool):
    order = reversed(vks) if up else vks
    _send([_key_input(vk, up) for vk in order])


def send_mouse(name: str, up: bool):
    if name in WHEEL_OUTPUTS:
        if not up:  # one scroll step per press
            data = WHEEL_OUTPUTS[name] & 0xFFFFFFFF
            mi = MOUSEINPUT(0, 0, data, MOUSEEVENTF_WHEEL, 0, 0)
            _send([INPUT(type=INPUT_MOUSE, u=_INPUTUNION(mi=mi))])
        return
    down_flag, up_flag, data = MOUSE_FLAGS[name]
    mi = MOUSEINPUT(0, 0, data, up_flag if up else down_flag, 0, 0)
    _send([INPUT(type=INPUT_MOUSE, u=_INPUTUNION(mi=mi))])


def _point_in_own_window(pt) -> bool:
    hwnd = user32.WindowFromPoint(pt)
    if not hwnd:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(user32.GetAncestor(hwnd, GA_ROOT), ctypes.byref(pid))
    return pid.value == _OWN_PID


# --- Remapper --------------------------------------------------------------

class Remapper:
    """Owns the hook thread and the worker thread.

    dpi_handler(action, pressed) is called for "dpi:*" actions and
    profile_handler(action) for "profile:*" actions (on press only). Both run
    on the worker thread, so they may talk to the mouse over USB.
    """

    def __init__(self, dpi_handler=None, profile_handler=None):
        self._map = {b: "default" for b in ALL_BUTTONS}
        self._held = {}  # button -> action used for the press, so the release matches
        self._dpi_handler = dpi_handler
        self._profile_handler = profile_handler
        self._queue = queue.Queue()
        self._thread = None
        self._thread_id = None
        self._hook = None
        self._proc = HOOKPROC(self._callback)  # keep a reference
        threading.Thread(target=self._worker, daemon=True, name="remap-worker").start()

    @property
    def hook_active(self) -> bool:
        return self._thread is not None

    def set_mapping(self, mapping: dict):
        for action in mapping.values():
            validate_action(action)
        new = {b: "default" for b in ALL_BUTTONS}
        new.update({b: a for b, a in mapping.items() if b in new})
        self._map = new
        if any(new[b] != "default" for b in HOOK_BUTTONS):
            self._start_hook()
        else:
            self._stop_hook()

    def stop(self):
        self._stop_hook()

    def external_event(self, button: str, pressed: bool):
        """Press / release of a driver-mode button (DPI up, DPI down, profile)."""
        action = self._map.get(button, "default")
        if action == "default":
            action = DRIVER_DEFAULTS.get(button, "disabled")
        self._dispatch(button, action, pressed)

    # --- hook thread --------------------------------------------------------

    def _start_hook(self):
        if self._thread:
            return
        ready = threading.Event()
        self._thread = threading.Thread(target=self._hook_loop, args=(ready,), daemon=True,
                                        name="mouse-hook")
        self._thread.start()
        ready.wait(2)

    def _stop_hook(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(2)
        self._thread = None

    def _hook_loop(self, ready):
        self._thread_id = kernel32.GetCurrentThreadId()
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc,
                                              kernel32.GetModuleHandleW(None), 0)
        ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(self._hook)
        self._hook = None
        self._thread_id = None

    def _callback(self, n_code, w_param, l_param):
        if n_code == HC_ACTION and w_param in _HOOK_MESSAGES:
            info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            if not info.flags & LLMHF_INJECTED and self._handle(w_param, info):
                return 1  # block the original event
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _handle(self, msg, info) -> bool:
        """Returns True when the original event must be blocked."""
        if msg == WM_MOUSEWHEEL:
            delta = ctypes.c_short(info.mouseData >> 16).value
            button = "wheel_up" if delta > 0 else "wheel_down"
            action = self._map[button]
            if action == "default" or _point_in_own_window(info.pt):
                return False
            for _ in range(max(1, abs(delta) // WHEEL_DELTA)):
                self._queue.put((action, True))
                self._queue.put((action, False))
            return True

        if msg in (WM_XBUTTONDOWN, WM_XBUTTONUP):
            button = "rear" if info.mouseData >> 16 == XBUTTON1 else "front"
            pressed = msg == WM_XBUTTONDOWN
        elif msg in _DOWN:
            button, pressed = _DOWN[msg], True
        else:
            button, pressed = _UP[msg], False

        if pressed:
            action = self._map[button]
            if action == "default" or _point_in_own_window(info.pt):
                return False
            self._held[button] = action
            self._queue.put((action, True))
            return True
        # Release: block it only when its press was blocked.
        action = self._held.pop(button, None)
        if action is None:
            return False
        self._queue.put((action, False))
        return True

    # --- worker ---------------------------------------------------------------

    def _dispatch(self, button, action, pressed):
        if pressed:
            self._held[button] = action
        else:
            action = self._held.pop(button, action)
        self._queue.put((action, pressed))

    def _worker(self):
        while True:
            action, pressed = self._queue.get()
            try:
                self._perform(action, pressed)
            except Exception as exc:  # never let one bad action stop the worker
                print(f"remap action {action!r} failed: {exc}")

    def _perform(self, action: str, pressed: bool):
        if action in ("disabled", "default"):
            return
        kind, _, arg = action.partition(":")
        if kind == "keys":
            send_keys(parse_keys(arg), up=not pressed)
        elif kind == "mouse":
            send_mouse(arg, up=not pressed)
        elif kind == "dpi" and self._dpi_handler:
            self._dpi_handler(arg, pressed)
        elif kind == "profile" and self._profile_handler and pressed:
            self._profile_handler(arg)
        elif kind == "run" and pressed:
            os.startfile(arg)  # Windows opens it with the program that belongs to the file type
