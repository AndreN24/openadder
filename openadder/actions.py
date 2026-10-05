"""What a button can do: the action catalog, plain-language descriptions, and key names.

Action strings are explained in remap.py. This module has no window code, so it is
easy to test.
"""

# (key, name, what "default" does)
BUTTONS = [
    ("left", "Left click", "left click"),
    ("right", "Right click", "right click"),
    ("middle", "Wheel click", "middle click"),
    ("wheel_up", "Scroll up", "scroll up"),
    ("wheel_down", "Scroll down", "scroll down"),
    ("front", "Front side button", "forward"),
    ("rear", "Rear side button", "back"),
    ("dpi_up", "DPI up", "DPI stage up"),
    ("dpi_down", "DPI down", "DPI stage down"),
    ("profile", "Profile (bottom)", "nothing"),
]
BUTTON_NAMES = {key: name for key, name, _ in BUTTONS}
DEFAULT_JOB = {key: what for key, _, what in BUTTONS}

# Menu categories: (category, [(label, action), ...])
CATALOG = [
    ("Mouse", [
        ("Left click", "mouse:left"),
        ("Right click", "mouse:right"),
        ("Middle click", "mouse:middle"),
        ("Back", "mouse:back"),
        ("Forward", "mouse:forward"),
        ("Scroll up", "mouse:wheel_up"),
        ("Scroll down", "mouse:wheel_down"),
    ]),
    ("DPI", [
        ("DPI stage up", "dpi:up"),
        ("DPI stage down", "dpi:down"),
        ("Next DPI stage", "dpi:cycle"),
        ("Sniper DPI (hold)", "dpi:sniper"),
    ]),
    ("Profile", [
        ("Next profile", "profile:next"),
        ("Previous profile", "profile:prev"),
    ]),
    ("Keyboard", [
        ("Copy", "keys:ctrl+c"),
        ("Paste", "keys:ctrl+v"),
        ("Cut", "keys:ctrl+x"),
        ("Undo", "keys:ctrl+z"),
        ("Redo", "keys:ctrl+y"),
    ]),
    ("Media", [
        ("Play / Pause", "keys:play_pause"),
        ("Next track", "keys:next_track"),
        ("Previous track", "keys:prev_track"),
        ("Volume up", "keys:volume_up"),
        ("Volume down", "keys:volume_down"),
        ("Mute", "keys:volume_mute"),
    ]),
]
_LABELS = {action: label for _, items in CATALOG for label, action in items}

ACTION_TEXT = {
    "disabled": "Does nothing.",
    "mouse:left": "Works as a left click.",
    "mouse:right": "Works as a right click.",
    "mouse:middle": "Works as a middle click (wheel click).",
    "mouse:back": "Goes back, like the back button of a web browser.",
    "mouse:forward": "Goes forward, like the forward button of a web browser.",
    "mouse:wheel_up": "Scrolls up one step for each press.",
    "mouse:wheel_down": "Scrolls down one step for each press.",
    "dpi:up": "Goes to the next higher DPI stage (faster pointer).",
    "dpi:down": "Goes to the next lower DPI stage (slower pointer).",
    "dpi:cycle": "Goes to the next DPI stage. After the last stage, it goes back to the first.",
    "dpi:sniper": "Uses the sniper DPI while you hold the button, for precise aiming.",
    "profile:next": "Switches to the next profile.",
    "profile:prev": "Switches to the previous profile.",
}

KEY_LABELS = {
    "ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "win": "Win",
    "volume_up": "Volume up", "volume_down": "Volume down", "volume_mute": "Mute",
    "play_pause": "Play/Pause", "next_track": "Next track", "prev_track": "Previous track",
    "media_stop": "Stop", "esc": "Esc", "pageup": "Page Up", "pagedown": "Page Down",
    "printscreen": "Print Screen", "capslock": "Caps Lock", "backspace": "Backspace",
    "minus": "-", "equals": "=", "comma": ",", "period": ".", "slash": "/",
}

MODIFIER_ORDER = ("ctrl", "shift", "alt", "win")


def pretty_keys(keys: str) -> str:
    """'ctrl+shift+t' -> 'Ctrl+Shift+T'."""
    def one(k):
        if k in KEY_LABELS:
            return KEY_LABELS[k]
        if len(k) == 1 or (k[0] == "f" and k[1:].isdigit()):
            return k.upper()
        return k.capitalize()

    return "+".join(one(k) for k in keys.lower().replace(" ", "").split("+") if k)


def label(key: str, action: str) -> str:
    """Short text for the button that shows the current action."""
    if action == "default":
        return f"Default ({DEFAULT_JOB[key]})"
    if action == "disabled":
        return "Disabled"
    if action in _LABELS:
        return _LABELS[action]
    if action.startswith("keys:"):
        return pretty_keys(action[5:])
    if action.startswith("run:"):
        return f"Run: {program_name(action[4:])}"
    return action


def describe(key: str, action: str) -> str:
    """One plain sentence that says what a button does."""
    if action == "default":
        return f"Does its normal job: {DEFAULT_JOB[key]}."
    if action.startswith("keys:"):
        return f"Presses {pretty_keys(action[5:])}."
    if action.startswith("run:"):
        return f"Starts {program_name(action[4:])}."
    return ACTION_TEXT.get(action, "")


def program_name(path: str) -> str:
    """Only the file name of a path, for example 'backup.bat'."""
    return path.replace("/", "\\").rsplit("\\", 1)[-1]


# --- Key recording ----------------------------------------------------------------
# Tk key names (keysyms) -> OpenAdder key names (see remap.NAMED_KEYS).

_KEYSYMS = {
    "Control_L": "ctrl", "Control_R": "ctrl", "Shift_L": "shift", "Shift_R": "shift",
    "Alt_L": "alt", "Alt_R": "alt", "Win_L": "win", "Win_R": "win", "Super_L": "win",
    "Super_R": "win", "Return": "enter", "KP_Enter": "enter", "Escape": "esc", "Tab": "tab",
    "space": "space", "BackSpace": "backspace", "Delete": "delete", "Insert": "insert",
    "Home": "home", "End": "end", "Prior": "pageup", "Next": "pagedown", "Up": "up",
    "Down": "down", "Left": "left", "Right": "right", "Print": "printscreen",
    "Caps_Lock": "capslock", "minus": "minus", "equal": "equals", "comma": "comma",
    "period": "period", "slash": "slash",
}


def keysym_to_name(keysym: str):
    """Tk keysym -> OpenAdder key name, or None if OpenAdder cannot send that key."""
    if keysym in _KEYSYMS:
        return _KEYSYMS[keysym]
    if len(keysym) == 1 and keysym.isalnum():
        return keysym.lower()
    if keysym[:1] in "Ff" and keysym[1:].isdigit() and 1 <= int(keysym[1:]) <= 24:
        return keysym.lower()
    return None


def combo(names) -> str:
    """Held key names -> 'ctrl+shift+t' (modifiers first, in a fixed order)."""
    mods = [m for m in MODIFIER_ORDER if m in names]
    keys = [n for n in names if n not in MODIFIER_ORDER]
    return "+".join(mods + keys)
