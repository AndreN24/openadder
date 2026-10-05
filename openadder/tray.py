"""Notification-area (tray) icon with a menu and a global shortcut, using the Windows API.

The icon runs on its own thread with a hidden window that receives its messages.
Callbacks run on that thread, so they should only hand work to the UI thread.
"""

import ctypes
import threading
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_DESTROY, WM_CLOSE, WM_HOTKEY = 0x0002, 0x0010, 0x0312
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x4000
VK_ESCAPE = 0x1B
WM_LBUTTONUP, WM_RBUTTONUP = 0x0202, 0x0205
WM_TRAY = 0x8000 + 1  # WM_APP + 1
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
NIIF_INFO = 0x1
MF_STRING, MF_POPUP, MF_SEPARATOR, MF_CHECKED, MF_DEFAULT = 0x0, 0x10, 0x800, 0x8, 0x1000
TPM_RETURNCMD, TPM_RIGHTBUTTON = 0x100, 0x2
IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x10, 0x40

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", wintypes.HICON)]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int,
                              ctypes.c_int, wintypes.UINT]
user32.LoadImageW.restype = wintypes.HANDLE
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wintypes.HWND, wintypes.LPVOID]
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class Separator:
    pass


class MenuItem:
    """text, a callback (or a list of MenuItem for a submenu), checked mark, bold default item."""

    def __init__(self, text, action, checked=False, default=False):
        self.text, self.action, self.checked, self.default = text, action, checked, default


class Tray:
    """menu() returns the menu items each time the menu opens, so it is always current.

    hotkey is (modifiers, virtual key); on_hotkey() runs when it is pressed anywhere.
    After start(), hotkey_ok says whether Windows gave us the shortcut.
    """

    def __init__(self, tooltip, icon_path, on_click, menu, hotkey=None, on_hotkey=None):
        self._tooltip = tooltip
        self._icon_path = icon_path
        self._on_click = on_click
        self._menu = menu
        self._hotkey = hotkey
        self._on_hotkey = on_hotkey
        self.hotkey_ok = False
        self._hwnd = None
        self._ready = threading.Event()
        self._proc = WNDPROC(self._wndproc)  # keep a reference
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="tray").start()
        self._ready.wait(5)

    def stop(self):
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)

    def notify(self, text, title):
        data = self._data(NIF_INFO)
        data.szInfo, data.szInfoTitle, data.dwInfoFlags = text[:255], title[:63], NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(data))

    def update_menu(self):
        """The menu is built when it opens, so there is nothing to do."""

    # --- window thread ----------------------------------------------------------

    def _data(self, flags):
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd, data.uID, data.uFlags = self._hwnd, 1, flags
        return data

    def _add_icon(self):
        data = self._data(NIF_MESSAGE | NIF_ICON | NIF_TIP)
        data.uCallbackMessage = WM_TRAY
        data.hIcon = self._icon
        data.szTip = self._tooltip[:127]
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data))

    def _run(self):
        hinst = kernel32.GetModuleHandleW(None)
        name = f"OpenAdderTray{id(self)}"  # one window class per icon
        wc = WNDCLASSW(lpfnWndProc=self._proc, hInstance=hinst, lpszClassName=name)
        user32.RegisterClassW(ctypes.byref(wc))
        self._hwnd = user32.CreateWindowExW(0, name, "OpenAdder tray", 0, 0, 0, 0, 0,
                                            None, None, hinst, None)
        self._icon = user32.LoadImageW(None, str(self._icon_path), IMAGE_ICON, 0, 0,
                                       LR_LOADFROMFILE | LR_DEFAULTSIZE)
        self._add_icon()
        if self._hotkey:
            self.hotkey_ok = bool(user32.RegisterHotKey(self._hwnd, 1, self._hotkey[0] | MOD_NOREPEAT,
                                                        self._hotkey[1]))
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY:
            if lparam & 0xFFFF == WM_LBUTTONUP:
                self._on_click()
            elif lparam & 0xFFFF == WM_RBUTTONUP:
                self._show_menu()
            return 0
        if msg == WM_HOTKEY and self._on_hotkey:
            self._on_hotkey()
            return 0
        if msg == self._taskbar_created:  # Explorer restarted: put the icon back
            self._add_icon()
            return 0
        if msg == WM_CLOSE:
            user32.UnregisterHotKey(hwnd, 1)
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._data(0)))
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _build(self, items, actions):
        menu = user32.CreatePopupMenu()
        for item in items:
            if isinstance(item, Separator):
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            elif isinstance(item.action, list):
                user32.AppendMenuW(menu, MF_POPUP, self._build(item.action, actions), item.text)
            else:
                actions.append(item.action)
                flags = MF_STRING | (MF_CHECKED if item.checked else 0) | \
                    (MF_DEFAULT if item.default else 0)
                user32.AppendMenuW(menu, flags, len(actions), item.text)
        return menu

    def _show_menu(self):
        actions = []
        menu = self._build(self._menu(), actions)
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self._hwnd)  # so the menu closes when you click elsewhere
        chosen = user32.TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON, pt.x, pt.y, 0,
                                       self._hwnd, None)
        user32.DestroyMenu(menu)  # also destroys the submenus
        if chosen:
            actions[chosen - 1]()
