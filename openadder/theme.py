"""Retro terminal look: dark background, phosphor green, monospace font, square edges.

Built on Tk's own "clam" theme, so no theme library is needed.
"""

import ctypes
import tkinter as tk
from tkinter import ttk

BG = "#0b0f0b"        # window
PANEL = BG            # tab pages use the window background
FIELD = "#0e150e"     # input fields
BORDER = "#24402a"
GREEN = "#44d62c"     # accent (phosphor green)
TEXT = "#c6f2be"
MUTED = "#6b9a66"
ERROR = "#ff6b5b"

FONT = ("Consolas", 10)
BOLD = ("Consolas", 10, "bold")


def dark_title_bar(window):
    """Asks Windows for a dark title bar (Windows 10 20H1 and later)."""
    window.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    value = ctypes.c_int(1)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))


def apply(root: tk.Tk):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=BG, foreground=TEXT, fieldbackground=FIELD, font=FONT,
                    bordercolor=BORDER, lightcolor=BG, darkcolor=BG, troughcolor=FIELD,
                    focuscolor=GREEN, selectbackground=GREEN, selectforeground=BG,
                    insertcolor=GREEN, arrowcolor=GREEN, relief="flat")
    style.map(".", foreground=[("disabled", MUTED)])

    # Text styles
    style.configure("Title.TLabel", font=("Consolas", 18, "bold"), foreground=GREEN)
    style.configure("Section.TLabel", font=BOLD, foreground=GREEN, background=PANEL)
    style.configure("Hint.TLabel", foreground=MUTED)
    style.configure("Caption.TLabel", foreground=TEXT)
    style.configure("Page.TFrame", background=PANEL)
    style.configure("Page.TLabel", background=PANEL)
    style.configure("PageHint.TLabel", background=PANEL, foreground=MUTED)

    # Buttons and menus
    for name in ("TButton", "TMenubutton", "Action.TMenubutton"):
        style.configure(name, background=FIELD, foreground=TEXT, bordercolor=BORDER,
                        padding=(10, 4), relief="solid", borderwidth=1)
        style.map(name, background=[("pressed", BORDER), ("active", "#16261a")],
                  bordercolor=[("focus", GREEN), ("active", GREEN)],
                  foreground=[("active", GREEN)])
    style.configure("Action.TMenubutton", anchor="w", width=26)
    style.configure("Accent.TButton", background=GREEN, foreground=BG, font=BOLD)
    style.map("Accent.TButton", background=[("active", "#5ee846"), ("disabled", BORDER)],
              foreground=[("active", BG), ("disabled", MUTED)])

    # Inputs
    for name in ("TCombobox", "TSpinbox", "TEntry"):
        style.configure(name, fieldbackground=FIELD, background=FIELD, foreground=TEXT,
                        bordercolor=BORDER, padding=3, arrowsize=12)
        style.map(name, bordercolor=[("focus", GREEN)], fieldbackground=[("readonly", FIELD)],
                  foreground=[("readonly", TEXT)], selectbackground=[("readonly", FIELD)],
                  selectforeground=[("readonly", GREEN)])
    for name in ("TCheckbutton", "TRadiobutton"):
        style.configure(name, background=PANEL, foreground=TEXT, indicatorbackground=FIELD,
                        indicatorforeground=GREEN, upperbordercolor=BORDER, lowerbordercolor=BORDER)
        style.map(name, indicatorbackground=[("selected", FIELD)],
                  background=[("active", PANEL)], foreground=[("active", GREEN)])
    style.configure("Horizontal.TScale", background=GREEN, troughcolor=FIELD, bordercolor=BORDER,
                    lightcolor=GREEN, darkcolor=GREEN, sliderlength=14)

    # Tabs
    style.configure("TNotebook", background=BG, bordercolor=BORDER, tabmargins=0)
    style.configure("TNotebook.Tab", background=BG, foreground=MUTED, bordercolor=BORDER,
                    padding=(16, 5), font=BOLD)
    style.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", GREEN)],
              lightcolor=[("selected", PANEL)])

    # Classic Tk parts: menus, combobox lists, dialogs
    root.configure(background=BG)
    for pattern, value in (("*Menu.background", FIELD), ("*Menu.foreground", TEXT),
                           ("*Menu.activeBackground", GREEN), ("*Menu.activeForeground", BG),
                           ("*Menu.relief", "flat"), ("*Menu.borderWidth", 1), ("*Menu.font", FONT),
                           ("*TCombobox*Listbox.background", FIELD),
                           ("*TCombobox*Listbox.foreground", TEXT),
                           ("*TCombobox*Listbox.selectBackground", GREEN),
                           ("*TCombobox*Listbox.selectForeground", BG),
                           ("*TCombobox*Listbox.font", FONT), ("*Toplevel.background", BG)):
        root.option_add(pattern, value)
