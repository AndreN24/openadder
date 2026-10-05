"""OpenAdder main window (tkinter, retro theme) with a tray icon.

All USB work runs on one background thread, so the window never waits for the mouse.
"""

import copy
import ctypes
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk


from . import __version__, config, protocol as p, theme
from .actions import BUTTON_NAMES, BUTTONS, CATALOG, describe, label
from .device import ButtonListener, DeathAdderV2, DeviceError
from .dialogs import NameDialog, RecordKeysDialog
from .mouse_art import MouseView, design_to_px
from .tray import MOD_ALT, MOD_CONTROL, MOD_SHIFT, VK_ESCAPE, MenuItem, Separator, Tray
from .remap import DRIVER_BUTTONS, Remapper, validate_action

_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
ICON = _BASE / "assets" / "openadder.ico"

EFFECTS = ["static", "breathing", "spectrum", "reactive", "off"]
EFFECTS_WITH_COLOR = {"static", "breathing", "reactive"}
ZONES = [("logo", "Logo", p.LOGO_LED), ("wheel", "Scroll wheel", p.SCROLL_WHEEL_LED)]

STATUS_SECONDS = 5


def _hex(color):
    return "#%02x%02x%02x" % tuple(color)


class App:
    def __init__(self, start_minimized=False):
        self.cfg = config.load()
        self.dev = None
        self._sniper_restore = None
        self._ui_queue = queue.Queue()
        self._jobs = queue.Queue()
        self._loading = True
        self._connecting = False
        self._driver_mode = False
        self._selected = None
        self._hover = None
        self._after = {}  # name -> pending after() id, for debouncing
        self._visible = not start_minimized

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(f"OpenAdder {__version__}")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.iconbitmap(default=str(ICON))
        theme.apply(self.root)

        self.remapper = Remapper(dpi_handler=self._handle_dpi_action,
                                 profile_handler=lambda a: self._ui_queue.put(("profile", a)))
        self.listener = ButtonListener(self.remapper.external_event)
        threading.Thread(target=self._io_loop, daemon=True, name="usb").start()

        self._build_ui()
        self.remapper.set_mapping(self.prof["buttons"])
        self._start_tray()
        config.refresh_autostart()
        self._loading = False

        if self._visible:
            self.root.deiconify()
            theme.dark_title_bar(self.root)
        else:
            self._release_art()
        self.connect()
        self._poll_id = self.root.after(50, self._poll_ui_queue)

    @property
    def prof(self) -> dict:
        """The active profile."""
        return self.cfg["profiles"][self.cfg["active_profile"]]

    # --- Threads ----------------------------------------------------------------

    def _io(self, job, done=None):
        """Runs job() on the USB thread, then done(result, error) on the UI thread."""
        self._jobs.put((job, done))

    def _io_loop(self):
        while True:
            job, done = self._jobs.get()
            try:
                result, error = job(), None
            except (DeviceError, OSError, ValueError) as exc:
                result, error = None, exc
            self._ui_queue.put(("done", done, result, error))

    def _debounce(self, name, ms, fn):
        if name in self._after:
            self.root.after_cancel(self._after[name])
        self._after[name] = self.root.after(ms, lambda: (self._after.pop(name, None), fn()))

    def _poll_ui_queue(self):
        try:
            while True:
                msg = self._ui_queue.get_nowait()
                kind = msg[0]
                if kind == "done":
                    _, done, result, error = msg
                    if isinstance(error, OSError):
                        self._lost()
                    if done:
                        done(result, error)
                    elif error:
                        self.set_status(str(error), error=True)
                elif kind == "show":
                    self.show()
                elif kind == "quit":
                    self.quit()
                    return
                elif kind == "status":
                    self.set_status(msg[1])
                elif kind == "switch":
                    self.switch_profile(msg[1])
                elif kind == "emergency":
                    self.emergency_reset()
                elif kind == "profile":
                    self._step_profile(1 if msg[1] == "next" else -1)
                elif kind == "dpi_stage":
                    self._loading = True
                    self.active_stage.set(msg[1])
                    self._loading = False
                    self.prof["dpi"]["active"] = msg[1]
                    self.set_status(f"DPI stage {msg[1]}: {msg[2]} DPI")
        except queue.Empty:
            pass
        self._poll_id = self.root.after(50 if self._visible else 250, self._poll_ui_queue)

    # --- UI layout ----------------------------------------------------------------

    def _build_ui(self):

        main = ttk.Frame(self.root, padding=(18, 14, 18, 12))
        main.grid(sticky="nsew")

        header = ttk.Frame(main)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Label(header, text="DeathAdder V2", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Profile").pack(side="left", padx=(24, 6))
        self.profile_var = tk.StringVar(value=self.cfg["active_profile"])
        self.profile_combo = ttk.Combobox(header, textvariable=self.profile_var, width=16,
                                          state="readonly")
        self.profile_combo.pack(side="left")
        self.profile_combo.bind("<<ComboboxSelected>>",
                                lambda _e: self.switch_profile(self.profile_var.get()))
        manage = ttk.Menubutton(header, text="Manage", width=9)
        menu = tk.Menu(manage, tearoff=False)
        menu.add_command(label="New profile", command=self.new_profile)
        menu.add_command(label="Duplicate profile", command=self.duplicate_profile)
        menu.add_command(label="Rename profile…", command=self.rename_profile)
        menu.add_command(label="Delete profile", command=self.delete_profile)
        menu.add_separator()
        menu.add_command(label="Reset this profile", command=self.reset_profile)
        menu.add_command(label="Reset everything…", command=self.reset_everything)
        manage["menu"] = menu
        manage.pack(side="left", padx=6)
        self.conn_label = ttk.Label(header, text="● Looking for the mouse…", style="Hint.TLabel")
        self.conn_label.pack(side="right")
        self._refresh_profile_list()

        # Mouse picture
        left = ttk.Frame(main)
        left.grid(row=1, column=0, sticky="n", padx=(0, 18))
        self.canvas = tk.Canvas(left, bg=theme.BG, highlightthickness=0)
        self.canvas.pack()
        self.view = MouseView(self.canvas)
        w, h = self.view.size
        self.canvas.configure(width=w, height=h)
        px, py = design_to_px(228, 424)
        self._pill_text = self.canvas.create_text(px, py, text="Profile (bottom)",
                                                  fill=theme.MUTED, font=("Consolas", 8))
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Leave>", lambda _e: self._set_hover(None))
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.caption = ttk.Label(left, text="", style="Caption.TLabel", width=44, anchor="center",
                                 justify="center", wraplength=w - 8)
        self.caption.pack(pady=(6, 0))

        # Tabs
        self.tabs = ttk.Notebook(main)
        self.tabs.grid(row=1, column=1, sticky="nsew")
        self.buttons_tab = self._build_buttons(self.tabs)
        self.tabs.add(self.buttons_tab, text="  Buttons  ")
        self.tabs.add(self._build_performance(self.tabs), text="  DPI  ")
        self.tabs.add(self._build_lighting(self.tabs), text="  Lighting  ")

        footer = ttk.Frame(main)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        self.autostart_var = tk.BooleanVar(value=config.autostart_enabled())
        ttk.Checkbutton(footer, text="Start with Windows", variable=self.autostart_var,
                        command=self.toggle_autostart).pack(side="left")
        ttk.Label(footer, text="Closing the window keeps OpenAdder running in the tray.",
                  style="Hint.TLabel").pack(side="left", padx=(12, 0))
        self.status = ttk.Label(footer, text="")
        self.status.pack(side="right")

        self._redraw()

    def _hint(self, parent, text, row, columnspan=3, pady=(0, 10)):
        ttk.Label(parent, text=text, style="Hint.TLabel", wraplength=440, justify="left").grid(
            row=row, column=0, columnspan=columnspan, sticky="w", pady=pady)

    def _reset_link(self, parent, text, command, row):
        ttk.Button(parent, text=text, command=command).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(14, 0))

    def _build_buttons(self, parent):
        frame = ttk.Frame(parent, padding=14)
        self._hint(frame, "Choose what each button does. Changes work at once. "
                          "OpenAdder must run for this; it can stay in the tray.", row=0)
        self.action_buttons, self.action_menus = {}, {}
        for i, (key, name, _what) in enumerate(BUTTONS):
            row = i + 1
            name_label = ttk.Label(frame, text=name, width=21)
            name_label.grid(row=row, column=0, sticky="w", pady=2)
            mb = ttk.Menubutton(frame, width=26, style="Action.TMenubutton")
            mb.grid(row=row, column=1, sticky="w", padx=(4, 0), pady=2)
            self.action_menus[key] = mb["menu"] = self._action_menu(mb, key)
            for widget in (name_label, mb):
                widget.bind("<Enter>", lambda _e, k=key: self._set_hover(k))
                widget.bind("<Leave>", lambda _e: self._set_hover(None))
            mb.bind("<FocusIn>", lambda _e, k=key: self._select(k))
            mb.bind("<Button-1>", lambda _e, k=key: self._select(k), add="+")
            self.action_buttons[key] = mb
        self._refresh_action_buttons()

        sniper = ttk.Frame(frame)
        sniper.grid(row=len(BUTTONS) + 1, column=0, columnspan=3, sticky="w", pady=(10, 0))
        ttk.Label(sniper, text="Sniper DPI").pack(side="left")
        self.sniper_var = tk.IntVar(value=self.prof["sniper_dpi"])
        ttk.Spinbox(sniper, from_=p.MIN_DPI, to=p.MAX_DPI, increment=50, width=7,
                    textvariable=self.sniper_var).pack(side="left", padx=8)
        self.sniper_var.trace_add("write", lambda *_: self._debounce("sniper", 600, self._save_sniper))
        ttk.Label(sniper, text="used by “Sniper DPI (hold)”", style="Hint.TLabel").pack(side="left")
        self._reset_link(frame, "Reset all buttons", self.reset_buttons, len(BUTTONS) + 2)
        self._hint(frame, "Emergency: Ctrl+Alt+Shift+Esc sets all buttons back to normal, "
                          "from anywhere.", row=len(BUTTONS) + 3, pady=(8, 0))
        return frame

    def _action_menu(self, parent, key):
        menu = tk.Menu(parent, tearoff=False)
        menu.add_command(label=label(key, "default"), command=lambda: self.set_action(key, "default"))
        if key != "left":  # never lose left click
            menu.add_command(label="Disabled", command=lambda: self.set_action(key, "disabled"))
        menu.add_separator()
        for category, items in CATALOG:
            sub = tk.Menu(menu, tearoff=False)
            for item_label, action in items:
                sub.add_command(label=item_label, command=lambda a=action: self.set_action(key, a))
            menu.add_cascade(label=category, menu=sub)
        menu.add_separator()
        menu.add_command(label="Record keys…", command=lambda: self.record_keys(key))
        menu.add_command(label="Run a program or script…", command=lambda: self.choose_program(key))
        return menu

    def _build_performance(self, parent):
        frame = ttk.Frame(parent, padding=14)
        ttk.Label(frame, text="DPI stages", style="Section.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w")
        self._hint(frame, "DPI is the speed of the pointer: a higher number is faster. "
                          "The DPI buttons on the mouse switch between the stages that are on.",
                   row=1, pady=(0, 8))
        self.stage_used, self.stage_dpi = [], []
        self.active_stage = tk.IntVar(value=1)
        for i in range(p.MAX_DPI_STAGES):
            used = tk.BooleanVar(value=True)
            dpi = tk.IntVar(value=800)
            ttk.Checkbutton(frame, text=f"Stage {i + 1}", variable=used).grid(
                row=i + 2, column=0, sticky="w", pady=3)
            ttk.Spinbox(frame, from_=p.MIN_DPI, to=p.MAX_DPI, increment=50, width=8,
                        textvariable=dpi).grid(row=i + 2, column=1, padx=10)
            ttk.Radiobutton(frame, text="Active", variable=self.active_stage, value=i + 1).grid(
                row=i + 2, column=2, sticky="w")
            self.stage_used.append(used)
            self.stage_dpi.append(dpi)
            for var in (used, dpi):
                var.trace_add("write", self._on_dpi_edit)
        self.active_stage.trace_add("write", self._on_dpi_edit)

        ttk.Label(frame, text="Polling rate", style="Section.TLabel").grid(
            row=8, column=0, sticky="w", pady=(16, 0))
        self._hint(frame, "How often the mouse reports to the PC. 1000 Hz is the smoothest.",
                   row=9, pady=(0, 6))
        self.poll_var = tk.StringVar(value="1000")
        poll = ttk.Frame(frame)
        poll.grid(row=10, column=0, columnspan=3, sticky="w")
        for hz in ("125", "500", "1000"):
            ttk.Radiobutton(poll, text=f"{hz} Hz", variable=self.poll_var, value=hz).pack(
                side="left", padx=(0, 14))
        self.poll_var.trace_add("write", self._on_dpi_edit)
        self._hint(frame, "Changes are saved on the mouse by themselves, so they also work "
                          "without OpenAdder.", row=11, pady=(16, 0))
        self._reset_link(frame, "Reset DPI and polling rate", self.reset_dpi, 12)
        return frame

    def _build_lighting(self, parent):
        frame = ttk.Frame(parent, padding=14)
        self._hint(frame, "Lighting is saved on the mouse, so it stays when OpenAdder is closed.",
                   row=0)
        self.zone_vars = {}
        for i, (key, zone_label, _led) in enumerate(ZONES):
            zcfg = self.prof["lighting"][key]
            effect = tk.StringVar(value=zcfg["effect"])
            color = list(zcfg["color"])
            bright = tk.IntVar(value=zcfg["brightness"])
            r = 1 + i * 4
            ttk.Label(frame, text=zone_label, style="Section.TLabel").grid(
                row=r, column=0, columnspan=3, sticky="w", pady=(0 if i == 0 else 16, 6))
            ttk.Label(frame, text="Effect").grid(row=r + 1, column=0, sticky="w")
            combo = ttk.Combobox(frame, textvariable=effect, values=EFFECTS, width=12,
                                 state="readonly")
            combo.grid(row=r + 1, column=1, sticky="w", padx=10, pady=3)
            combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_lighting())
            swatch = tk.Label(frame, width=4, bg=_hex(color), relief="flat",
                              highlightthickness=1, highlightbackground=theme.BORDER)
            swatch.grid(row=r + 1, column=2, sticky="w")
            swatch.bind("<Button-1>", lambda _e, k=key: self.pick_color(k))
            ttk.Label(frame, text="Brightness").grid(row=r + 2, column=0, sticky="w")
            ttk.Scale(frame, from_=0, to=255, variable=bright, length=170,
                      command=lambda _v: self._on_brightness()).grid(
                row=r + 2, column=1, columnspan=2, sticky="w", padx=10, pady=3)
            self.zone_vars[key] = {"effect": effect, "color": color, "bright": bright,
                                   "swatch": swatch}
        self._hint(frame, "Click the colour box to choose a colour. Spectrum cycles through all "
                          "colours. Reactive lights up when you click.", row=10, pady=(16, 0))
        self._reset_link(frame, "Reset lighting", self.reset_lighting, 11)
        self._refresh_swatches()
        return frame

    # --- Mouse picture ----------------------------------------------------------------

    def _lighting(self):
        return {k: (z["effect"].get(), tuple(z["color"]), int(float(z["bright"].get())))
                for k, z in self.zone_vars.items()}

    def _release_art(self):
        """Frees the picture while the window is hidden; show() loads it again."""
        if self.view:
            self.view.destroy()
            self.view = None

    def _redraw(self):
        if self.view is None:
            return
        self.view.set_lighting(self._lighting())
        self.view.set_highlight(self._hover or self._selected)  # one at a time
        self.canvas.tag_raise(self._pill_text)
        key = self._hover or self._selected
        if key:
            self.caption.configure(text=f"{BUTTON_NAMES[key]}\n"
                                        f"{describe(key, self.prof['buttons'][key])}")
        else:
            self.caption.configure(text="Point at the mouse to see what a button does.\n"
                                        "Click a button to change it.")

    def _set_hover(self, key):
        if key != self._hover:
            self._hover = key
            self._redraw()

    def _select(self, key):
        if key != self._selected:
            self._selected = key
            self._redraw()

    def _on_canvas_motion(self, event):
        key = self.view.hit(event.x, event.y) if self.view else None
        self.canvas.configure(cursor="hand2" if key else "")
        self._set_hover(key)

    def _on_canvas_click(self, event):
        key = self.view.hit(event.x, event.y) if self.view else None
        if key:
            self._select(key)
            self.tabs.select(self.buttons_tab)
            mb = self.action_buttons[key]
            mb.focus_set()
            mb.update_idletasks()
            self.action_menus[key].tk_popup(mb.winfo_rootx(), mb.winfo_rooty() + mb.winfo_height())

    def set_status(self, text, error=False):
        self.status.configure(text=text, foreground=theme.ERROR if error else theme.GREEN)
        self._debounce("status", STATUS_SECONDS * 1000, lambda: self.status.configure(text=""))

    # --- Device -------------------------------------------------------------------------

    def connect(self, quiet=False):
        if self._connecting:
            return
        self._connecting = True
        old, self.dev = self.dev, None

        def job():
            self.listener.stop()
            if old:
                old.close()
            dev = DeathAdderV2.open()
            info = {"dev": dev, "fw": dev.firmware(), "poll": dev.poll_rate(),
                    "bright": {k: dev.brightness(led) for k, _, led in ZONES}}
            info["stages"], info["active"] = dev.dpi_stages()
            if dev.device_mode() != p.NORMAL_MODE:  # left over from a crash
                dev.set_device_mode(p.NORMAL_MODE)
            return info

        def done(info, error):
            self._connecting = False
            self._driver_mode = False
            if error:
                self.conn_label.configure(text="● Mouse not found: plug it in. "
                                               "OpenAdder connects by itself.",
                                          foreground=theme.ERROR)
                self._debounce("reconnect", 3000, lambda: self.connect(quiet=True))
                return
            self.dev = info["dev"]
            self.conn_label.configure(text=f"● Connected · firmware {info['fw']}",
                                      foreground=theme.GREEN)
            self._take_mouse_values(info)
            self._sync_driver_mode()
            if quiet:
                self.set_status("Mouse connected.")

        self._io(job, done)

    def _take_mouse_values(self, info):
        """The mouse holds the real DPI, polling rate and brightness: show them."""
        prof = self.prof
        prof["dpi"] = {"stages": [x for x, _ in info["stages"]], "active": max(1, info["active"])}
        prof["poll"] = info["poll"] or prof["poll"]
        for key, value in info["bright"].items():
            prof["lighting"][key]["brightness"] = value
        self._load_profile_into_ui()

    def refresh_from_mouse(self):
        dev = self.dev
        if not dev:
            return

        def job():
            stages, active = dev.dpi_stages()
            return {"stages": stages, "active": active, "poll": dev.poll_rate(),
                    "bright": {k: dev.brightness(led) for k, _, led in ZONES}}

        self._io(job, lambda info, err: None if err else self._take_mouse_values(info))

    def _lost(self):
        if not self.dev:
            return
        self.listener.stop()
        self.dev = None
        self._driver_mode = False
        self.conn_label.configure(text="● Mouse disconnected: plug it in. "
                                       "OpenAdder connects by itself.", foreground=theme.ERROR)
        self._debounce("reconnect", 3000, lambda: self.connect(quiet=True))

    def _sync_driver_mode(self):
        """Driver mode is on only while a DPI or profile button is remapped."""
        need = any(self.prof["buttons"][b] != "default" for b in DRIVER_BUTTONS)
        dev = self.dev
        if not dev or need == self._driver_mode:
            return
        self._driver_mode = need

        def job():
            if need:
                dev.set_device_mode(p.DRIVER_MODE)
                self.listener.start()
            else:
                self.listener.stop()
                dev.set_device_mode(p.NORMAL_MODE)

        self._io(job)

    # --- Buttons ------------------------------------------------------------------------------

    def _refresh_action_buttons(self):
        for key, mb in self.action_buttons.items():
            mb.configure(text=label(key, self.prof["buttons"][key]))

    def set_action(self, key, action):
        validate_action(action)
        if key == "left" and action != "default" and not messagebox.askyesno(
                "OpenAdder", "Change the left mouse button?\n\nIt will do the new action "
                "everywhere, except inside the OpenAdder window. You can change it back here "
                "at any time.\n\nEmergency: press Ctrl+Alt+Shift+Esc to set all buttons back to "
                "normal, from anywhere.", parent=self.root):
            return
        self.prof["buttons"][key] = action
        self._apply_buttons()
        self.set_status(f"{BUTTON_NAMES[key]}: {label(key, action)}")

    def _apply_buttons(self):
        self.remapper.set_mapping(self.prof["buttons"])
        self._sync_driver_mode()
        self._refresh_action_buttons()
        self._redraw()
        config.save(self.cfg)

    def record_keys(self, key):
        keys = RecordKeysDialog(self.root, BUTTON_NAMES[key]).run()
        if keys:
            self.set_action(key, f"keys:{keys}")

    def choose_program(self, key):
        path = filedialog.askopenfilename(
            parent=self.root, title=f"Program or script for: {BUTTON_NAMES[key]}",
            filetypes=[("Programs and scripts", "*.exe *.bat *.cmd *.ps1 *.py *.pyw *.lnk *.vbs"),
                       ("All files", "*.*")])
        if path:
            self.set_action(key, f"run:{Path(path)}")

    def _save_sniper(self):
        try:
            sniper = int(self.sniper_var.get())
        except (ValueError, tk.TclError):
            sniper = 0
        if not p.MIN_DPI <= sniper <= p.MAX_DPI:
            self.set_status(f"Sniper DPI: use a number from {p.MIN_DPI} to {p.MAX_DPI}.", error=True)
            return
        if sniper != self.prof["sniper_dpi"]:
            self.prof["sniper_dpi"] = sniper
            config.save(self.cfg)
            self.set_status(f"Sniper DPI: {sniper}")

    def _handle_dpi_action(self, action: str, pressed: bool):
        """Runs on the remap worker thread."""
        dev = self.dev
        if not dev:
            return
        if action in ("up", "down", "cycle") and pressed:
            stages, active = dev.dpi_stages()
            if not stages:
                return
            n = len(stages)
            nxt = {"up": min(active + 1, n), "down": max(active - 1, 1),
                   "cycle": active % n + 1}[action]
            if nxt != active:
                dev.set_dpi_stages(stages, nxt)
                dev.set_dpi(*stages[nxt - 1])
            self._ui_queue.put(("dpi_stage", nxt, stages[nxt - 1][0]))
        elif action == "sniper":
            if pressed and self._sniper_restore is None:
                self._sniper_restore = dev.dpi()
                dev.set_dpi(self.prof["sniper_dpi"])
            elif not pressed and self._sniper_restore is not None:
                dev.set_dpi(*self._sniper_restore)
                self._sniper_restore = None

    # --- DPI ------------------------------------------------------------------------------

    def _on_dpi_edit(self, *_):
        if not self._loading:
            self._debounce("dpi", 700, self._save_dpi)

    def read_dpi_form(self):
        """The DPI tab as (stages, active, poll). Raises ValueError with a plain message."""
        chosen = []
        for i in range(p.MAX_DPI_STAGES):
            if self.stage_used[i].get():
                try:
                    dpi = int(self.stage_dpi[i].get())
                except (ValueError, tk.TclError):
                    dpi = 0
                if not p.MIN_DPI <= dpi <= p.MAX_DPI:
                    raise ValueError(f"Stage {i + 1}: use a number from {p.MIN_DPI} to {p.MAX_DPI}.")
                chosen.append((i + 1, dpi))
        if not chosen:
            raise ValueError("Turn on at least one DPI stage.")
        rows = [row for row, _ in chosen]
        active_row = self.active_stage.get()
        active = rows.index(active_row) + 1 if active_row in rows else 1
        return [dpi for _, dpi in chosen], active, int(self.poll_var.get())

    def _save_dpi(self):
        try:
            stages, active, poll = self.read_dpi_form()
        except ValueError as exc:
            self.set_status(str(exc), error=True)
            return
        new = {"stages": stages, "active": active}
        if new == self.prof["dpi"] and poll == self.prof["poll"]:
            return
        self.prof["dpi"], self.prof["poll"] = new, poll
        config.save(self.cfg)
        dev = self.dev
        if not dev:
            self.set_status("Saved. The mouse gets it when it is connected.")
            return

        def job():
            dev.set_dpi_stages([(d, d) for d in stages], active)
            dev.set_dpi(stages[active - 1])
            dev.set_poll_rate(poll)

        self._io(job, lambda _r, e: self.set_status(str(e) if e else "DPI saved on the mouse.",
                                                     error=bool(e)))

    # --- Lighting ---------------------------------------------------------------------------

    def _refresh_swatches(self):
        """The colour box shows the colour only for effects that use one."""
        for z in self.zone_vars.values():
            has_color = z["effect"].get() in EFFECTS_WITH_COLOR
            z["swatch"].configure(bg=_hex(z["color"]) if has_color else theme.BG,
                                  cursor="hand2" if has_color else "")

    def _on_brightness(self):
        self._redraw()  # live preview while dragging
        self._debounce("lighting", 250, self.apply_lighting)

    def pick_color(self, key):
        zone = self.zone_vars[key]
        if zone["effect"].get() not in EFFECTS_WITH_COLOR:
            self.set_status("This effect has no colour. Choose static, breathing or reactive.")
            return
        _, hex_color = colorchooser.askcolor(color=_hex(zone["color"]), parent=self.root)
        if hex_color:
            zone["color"][:] = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
            self.apply_lighting()

    def apply_lighting(self):
        lighting = self._lighting()
        for key, (effect, color, bright) in lighting.items():
            self.prof["lighting"][key] = {"effect": effect, "color": list(color), "brightness": bright}
        config.save(self.cfg)
        self._refresh_swatches()
        self._redraw()
        dev = self.dev
        if not dev:
            self.set_status("Saved. The mouse gets it when it is connected.")
            return

        def job():
            for key, _label, led in ZONES:
                effect, color, bright = lighting[key]
                dev.set_effect(led, effect, color)
                dev.set_brightness(led, bright)

        self._io(job, lambda _r, e: self.set_status(str(e) if e else "Lighting saved on the mouse.",
                                                     error=bool(e)))

    # --- Profiles -------------------------------------------------------------------------------

    def _refresh_profile_list(self):
        self.profile_combo.configure(values=list(self.cfg["profiles"]))
        self.profile_var.set(self.cfg["active_profile"])
        if getattr(self, "tray", None):
            self.tray.update_menu()

    def _load_profile_into_ui(self):
        self._loading = True
        prof = self.prof
        self._refresh_action_buttons()
        self.sniper_var.set(prof["sniper_dpi"])
        stages = prof["dpi"]["stages"]
        for i in range(p.MAX_DPI_STAGES):
            self.stage_used[i].set(i < len(stages))
            if i < len(stages):
                self.stage_dpi[i].set(stages[i])
        self.active_stage.set(prof["dpi"]["active"])
        self.poll_var.set(str(prof["poll"]))
        for key, z in self.zone_vars.items():
            zcfg = prof["lighting"][key]
            z["effect"].set(zcfg["effect"])
            z["color"][:] = zcfg["color"]
            z["bright"].set(zcfg["brightness"])
        self._refresh_swatches()
        self._loading = False
        self._redraw()

    def _apply_profile_to_mouse(self):
        dev = self.dev
        if not dev:
            return
        prof = copy.deepcopy(self.prof)

        def job():
            stages = prof["dpi"]["stages"]
            active = max(1, min(prof["dpi"]["active"], len(stages)))
            dev.set_dpi_stages([(d, d) for d in stages], active)
            dev.set_dpi(stages[active - 1])
            dev.set_poll_rate(prof["poll"])
            for key, _label, led in ZONES:
                zcfg = prof["lighting"][key]
                dev.set_effect(led, zcfg["effect"], tuple(zcfg["color"]))
                dev.set_brightness(led, zcfg["brightness"])

        self._io(job)

    def switch_profile(self, name):
        if name not in self.cfg["profiles"]:
            return
        self.cfg["active_profile"] = name
        self._load_profile_into_ui()
        self.remapper.set_mapping(self.prof["buttons"])
        self._sync_driver_mode()
        self._apply_profile_to_mouse()
        config.save(self.cfg)
        self._refresh_profile_list()
        self.set_status(f"Profile “{name}” is active.")

    def _step_profile(self, step):
        names = list(self.cfg["profiles"])
        i = names.index(self.cfg["active_profile"])
        self.switch_profile(names[(i + step) % len(names)])

    def _ask_name(self, title, prompt, initial=""):
        def check(name):
            if name in self.cfg["profiles"] and name != initial:
                return f"A profile named “{name}” already exists."
            return None
        return NameDialog(self.root, title, prompt, initial, check).run()

    def new_profile(self):
        name = self._ask_name("New profile", "Name of the new profile. "
                              "It starts with the factory settings.")
        if name:
            self.cfg["profiles"][name] = config.default_profile()
            self.switch_profile(name)

    def duplicate_profile(self):
        name = self._ask_name("Duplicate profile", "Name of the copy:",
                              f"{self.cfg['active_profile']} copy")
        if name:
            self.cfg["profiles"][name] = copy.deepcopy(self.prof)
            self.switch_profile(name)

    def rename_profile(self):
        old = self.cfg["active_profile"]
        name = self._ask_name("Rename profile", "New name:", old)
        if name and name != old:
            self.cfg["profiles"] = {(name if k == old else k): v
                                    for k, v in self.cfg["profiles"].items()}
            self.cfg["active_profile"] = name
            config.save(self.cfg)
            self._refresh_profile_list()

    def delete_profile(self):
        name = self.cfg["active_profile"]
        if len(self.cfg["profiles"]) == 1:
            self.set_status("You cannot delete the last profile.", error=True)
            return
        if messagebox.askyesno("OpenAdder", f"Delete the profile “{name}”?", parent=self.root):
            del self.cfg["profiles"][name]
            self.switch_profile(next(iter(self.cfg["profiles"])))

    # --- Reset ---------------------------------------------------------------------------------

    def emergency_reset(self):
        """Ctrl+Alt+Shift+Esc, from anywhere: every button does its normal job again."""
        self.prof["buttons"] = config.default_profile()["buttons"]
        self._apply_buttons()
        self.tray.notify("All buttons are back to normal (Ctrl+Alt+Shift+Esc).", "OpenAdder")
        self.set_status("Emergency shortcut: all buttons are back to normal.")

    def reset_buttons(self):
        if messagebox.askyesno("OpenAdder", "Set all buttons back to their normal job?",
                               parent=self.root):
            self.prof["buttons"] = config.default_profile()["buttons"]
            self._apply_buttons()
            self.set_status("All buttons are back to normal.")

    def reset_dpi(self):
        factory = config.default_profile()
        self._loading = True
        for i, dpi in enumerate(factory["dpi"]["stages"]):
            self.stage_used[i].set(True)
            self.stage_dpi[i].set(dpi)
        self.active_stage.set(factory["dpi"]["active"])
        self.poll_var.set(str(factory["poll"]))
        self._loading = False
        self._save_dpi()

    def reset_lighting(self):
        factory = config.default_profile()["lighting"]
        for key, z in self.zone_vars.items():
            z["effect"].set(factory[key]["effect"])
            z["color"][:] = factory[key]["color"]
            z["bright"].set(factory[key]["brightness"])
        self.apply_lighting()

    def reset_profile(self):
        name = self.cfg["active_profile"]
        if messagebox.askyesno("OpenAdder",
                               f"Reset all settings of “{name}” to the factory settings?\n\n"
                               "This resets the buttons, DPI, polling rate and lighting.",
                               parent=self.root):
            self.cfg["profiles"][name] = config.default_profile()
            self.switch_profile(name)
            self.set_status(f"“{name}” is back to the factory settings.")

    def reset_everything(self):
        if not messagebox.askyesno(
                "OpenAdder", "Reset everything?\n\nThis deletes all profiles, sets the mouse back "
                "to its factory settings, and turns off “Start with Windows”.", parent=self.root):
            return
        self.cfg = config.factory_settings()
        config.set_autostart(False)
        self.autostart_var.set(False)
        self.switch_profile(config.DEFAULT_PROFILE_NAME)
        self.set_status("Everything is back to the factory settings.")

    # --- Autostart, tray, window ------------------------------------------------------------------

    def toggle_autostart(self):
        try:
            config.set_autostart(self.autostart_var.get())
        except OSError as exc:
            self.set_status(f"Could not change autostart: {exc}", error=True)
            self.autostart_var.set(config.autostart_enabled())

    def _start_tray(self):
        def switch_to(name):
            return lambda: self._ui_queue.put(("switch", name))

        def menu():
            profiles = [MenuItem(name, switch_to(name), checked=name == self.cfg["active_profile"])
                        for name in self.cfg["profiles"]]
            return [MenuItem("Open OpenAdder", lambda: self._ui_queue.put(("show",)), default=True),
                    MenuItem("Profile", profiles),
                    Separator(),
                    MenuItem("Quit", lambda: self._ui_queue.put(("quit",)))]

        self.tray = Tray("OpenAdder", ICON, lambda: self._ui_queue.put(("show",)), menu,
                         hotkey=(MOD_CONTROL | MOD_ALT | MOD_SHIFT, VK_ESCAPE),
                         on_hotkey=lambda: self._ui_queue.put(("emergency",)))
        self.tray.start()
        if not self.tray.hotkey_ok:
            self.root.after(500, lambda: self.set_status(
                "Another program uses Ctrl+Alt+Shift+Esc, so the emergency shortcut is off.", error=True))

    def show(self):
        self._visible = True
        if self.view is None:
            self.view = MouseView(self.canvas)
            self._redraw()
        self.root.deiconify()
        theme.dark_title_bar(self.root)
        self.root.lift()
        self.root.focus_force()
        self.refresh_from_mouse()

    def on_close(self):
        self._visible = False
        self.root.withdraw()  # keep running in the tray so the buttons keep working
        self._release_art()
        if not self.cfg["tray_tip_shown"]:
            self.tray.notify("OpenAdder is still running here, so your buttons keep working. "
                             "Right-click this icon to quit.", "OpenAdder")
            self.cfg["tray_tip_shown"] = True
            config.save(self.cfg)

    def quit(self):
        self.remapper.stop()
        self.listener.stop()
        if self.dev:
            if self._driver_mode:  # give the DPI buttons back to the firmware
                try:
                    self.dev.set_device_mode(p.NORMAL_MODE)
                except (DeviceError, OSError):
                    pass
            self.dev.close()
        self.tray.stop()
        for after_id in [self._poll_id, *self._after.values()]:
            self.root.after_cancel(after_id)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateEventW.restype = ctypes.c_void_p
    kernel32.SetEvent.argtypes = [ctypes.c_void_p]
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    # The first copy owns the mutex. A second start only asks the first copy to show its window.
    mutex = kernel32.CreateMutexW(None, False, "Local\\OpenAdder")
    first = ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS
    show_event = kernel32.CreateEventW(None, False, False, "Local\\OpenAdder.Show")
    if not first:
        kernel32.SetEvent(show_event)
        return
    app = App(start_minimized="--minimized" in sys.argv)

    def wait_for_show():
        while kernel32.WaitForSingleObject(show_event, 0xFFFFFFFF) == 0:
            app._ui_queue.put(("show",))

    threading.Thread(target=wait_for_show, daemon=True, name="show").start()
    app.run()
    del mutex
