"""Small themed dialogs: type a name, and record a key combination."""

import tkinter as tk
from tkinter import ttk

from . import theme
from .actions import combo, keysym_to_name, pretty_keys


class _Dialog(tk.Toplevel):
    """Modal dialog centred on its parent, in the same theme as the main window."""

    def __init__(self, parent, title):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.result = None
        self.body = ttk.Frame(self, padding=18)
        self.body.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self.cancel)

    def run(self):
        self.update_idletasks()
        p = self.master
        x = p.winfo_rootx() + (p.winfo_width() - self.winfo_reqwidth()) // 2
        y = p.winfo_rooty() + (p.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.deiconify()
        theme.dark_title_bar(self)
        self.grab_set()
        self.focus_force()
        self.wait_window()
        return self.result

    def buttons(self, ok_text, ok_command):
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=(16, 0))
        ttk.Button(row, text="Cancel", command=self.cancel).pack(side="right")
        self.ok = ttk.Button(row, text=ok_text, style="Accent.TButton", command=ok_command)
        self.ok.pack(side="right", padx=(0, 8))

    def cancel(self):
        self.result = None
        self.destroy()


class NameDialog(_Dialog):
    """Asks for a name. check(name) returns an error text, or None if the name is fine."""

    def __init__(self, parent, title, prompt, initial="", check=None):
        super().__init__(parent, title)
        self._check = check or (lambda name: None)
        ttk.Label(self.body, text=prompt).pack(anchor="w")
        self.var = tk.StringVar(value=initial)
        entry = ttk.Entry(self.body, textvariable=self.var, width=36)
        entry.pack(fill="x", pady=(8, 0))
        entry.select_range(0, "end")
        entry.focus_set()
        self.error = ttk.Label(self.body, text="", foreground=theme.ERROR)
        self.error.pack(anchor="w", pady=(6, 0))
        self.buttons("OK", self.accept)
        self.bind("<Return>", lambda _e: self.accept())
        self.bind("<Escape>", lambda _e: self.cancel())

    def accept(self):
        name = self.var.get().strip()
        problem = "Type a name." if not name else self._check(name)
        if problem:
            self.error.configure(text=problem)
            return
        self.result = name
        self.destroy()


class RecordKeysDialog(_Dialog):
    """Records a key combination: the user presses it, sees it, and clicks Save."""

    def __init__(self, parent, button_name):
        super().__init__(parent, "Record keys")
        self._held = []      # key names held right now, in press order
        self._recorded = ""  # the last complete combination
        ttk.Label(self.body, text=f"Press the keys for: {button_name}",
                  style="Title.TLabel", font=theme.BOLD).pack(anchor="w")
        ttk.Label(self.body, text="For example Ctrl+Shift+T. Hold the keys together, then let go.",
                  style="Hint.TLabel").pack(anchor="w", pady=(2, 12))
        self.display = ttk.Label(self.body, text="Waiting for keys…", anchor="center",
                                 style="Title.TLabel", font=("Consolas", 22, "bold"), width=18)
        self.display.pack(fill="x", ipady=12)
        self.note = ttk.Label(self.body, text="", style="Hint.TLabel")
        self.note.pack(anchor="w", pady=(10, 0))
        self.buttons("Save", self.accept)
        self.ok.state(["disabled"])
        self.bind("<KeyPress>", self._press)
        self.bind("<KeyRelease>", self._release)

    def _press(self, event):
        name = keysym_to_name(event.keysym)
        if name is None:
            self.note.configure(text=f"OpenAdder cannot send the key “{event.keysym}”. "
                                     "Use the Media menu for media keys.")
            return "break"
        if name not in self._held:
            self._held.append(name)
        keys = combo(self._held)
        self.display.configure(text=pretty_keys(keys))
        if any(k not in ("ctrl", "shift", "alt", "win") for k in self._held):
            self._recorded = keys
            self.ok.state(["!disabled"])
            self.note.configure(text="Click Save, or press other keys to try again.")
        return "break"  # keep Alt, Tab and Enter from acting on the dialog

    def _release(self, event):
        name = keysym_to_name(event.keysym)
        if name in self._held:
            self._held.remove(name)
        if not self._held and self._recorded:
            self.display.configure(text=pretty_keys(self._recorded))
        return "break"

    def accept(self):
        if self._recorded:
            self.result = self._recorded
            self.destroy()
