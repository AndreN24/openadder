# Developing OpenAdder

## Layout

| Path | What it is |
|---|---|
| `OpenAdder.pyw` | Starts the app. |
| `openadder/gui.py` | The window, profiles, and the USB worker thread. |
| `openadder/actions.py` | What a button can do: the action menu, descriptions, key names. |
| `openadder/remap.py` | The remap engine: a Windows low-level mouse hook and `SendInput`. |
| `openadder/device.py` | USB transport (hidapi) and the driver-mode button listener. |
| `openadder/protocol.py` | The 90-byte Razer HID reports. |
| `openadder/config.py` | `%APPDATA%\OpenAdder\config.json` and the autostart entry. |
| `openadder/mouse_art.py` | The mouse picture as layers on a Tk canvas, plus a tiny PNG writer. |
| `openadder/tray.py` | Tray icon, tray menu and the emergency shortcut (Windows API through ctypes). |
| `openadder/theme.py` | The retro look, built on Tk's "clam" theme. |
| `openadder/dialogs.py` | Name and record-keys dialogs. |
| `tools/build_art.py` | Renders the mouse picture into `openadder/assets/art`. |
| `tools/build_icon.py` | Draws `assets/openadder.ico`. |
| `installer/OpenAdder.iss` | Inno Setup script for the installer. |

The only third-party library the app uses is [hidapi](https://github.com/trezor/cython-hidapi).
Everything else is the Python standard library and Tk.

## Run from source

```
py -m pip install -r requirements.txt
py OpenAdder.pyw
```

## Tests

```
py -m unittest discover -s tests -t .
```

The tests use a simulated mouse, a fake tray and a temporary settings folder. They do not change the real mouse,
your settings or your autostart entry. Two tests need a Windows desktop session (real tray icon, real mouse hook);
they are skipped when the environment variable `CI` is set.

Coverage (needs `requirements-dev.txt`):

```
py -m coverage run --source=openadder -m unittest discover -s tests -t .
py -m coverage report
```

## Build

Double-click `build.bat`. The first build makes a clean environment (`.venv-build`) with only the libraries in
`requirements.txt`, so nothing else from your Python installation ends up in the app. The result is
`dist\OpenAdder\OpenAdder.exe` (about 13 MB as a folder).

After a change to the mouse picture or the icon, run `py tools\build_art.py` or `py tools\build_icon.py` first.
These tools need Pillow (`requirements-dev.txt`); the app itself does not.

## Release

1. Update `__version__` in `openadder/__init__.py` and `CHANGELOG.md`.
2. Commit, then tag and push: `git tag v1.0.0` and `git push origin v1.0.0`.
3. The **Release** workflow tests, builds the app, the portable zip and the installer, and publishes them on the
   Releases page.

## How OpenAdder talks to the mouse

The mouse takes 90-byte HID feature reports on USB interface 0, through the standard Windows HID driver:

| Byte | Meaning |
|---|---|
| 0 | status (0x00 new, 0x02 OK, 0x01 busy, 0x03 failure, 0x05 not supported) |
| 1 | transaction id (0x3F for the DeathAdder V2) |
| 5 | number of argument bytes |
| 6, 7 | command class and id (bit 7 of the id means "read") |
| 8–87 | arguments |
| 88 | XOR of bytes 2–87 |

**Driver mode** (command 0x00/0x04, argument 0x03) makes the DPI and profile buttons report to the PC as
"report 4" on interface 1 (`0x20` DPI up, `0x21` DPI down, `0x50` profile). OpenAdder turns driver mode on only
while one of these buttons is remapped, and turns it off when it quits.

**Button remaps are not stored on the mouse.** The read command for the button table (class 0x02, id 0x8C) works,
but the matching write command (0x0C) is accepted and then ignored. The real write command is not publicly known.

## Adding another Razer mouse

Most Razer mice use the same report format. A new model needs:

1. Its USB product id and transaction id, DPI range, lighting zones and polling-rate command
   (OpenRazer's `driver/razermouse_driver.c` lists these for about 100 mice).
2. Its DPI-button codes in driver mode, if it has DPI buttons.
3. A picture (or a plain list of buttons) for the window.
4. A test on the real mouse.

## Ideas that were checked and left out

- **A C# rewrite:** measured idle memory was only about 2 MB lower; not worth the rewrite.
- **Mac support:** different hook, USB access, tray and packaging, and no way to test.
- **Macros, Hypershift, surface calibration:** left out to keep OpenAdder small.
