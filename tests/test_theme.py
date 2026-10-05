import tkinter as tk
import unittest
from tkinter import ttk

from openadder import theme


class Theme(unittest.TestCase):
    def test_apply_and_dark_title_bar(self):
        root = tk.Tk()
        root.update()
        self.addCleanup(root.destroy)
        theme.apply(root)
        style = ttk.Style(root)
        self.assertEqual(style.theme_use(), "clam")
        self.assertEqual(style.lookup("Title.TLabel", "foreground"), theme.GREEN)
        self.assertEqual(root.cget("background"), theme.BG)
        theme.dark_title_bar(root)  # must not fail


if __name__ == "__main__":
    unittest.main()
