"""Windows 11 (Fluent / Sun Valley) look: light & dark palettes, fonts, title bar colour."""
from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk

import sv_ttk

FONT = "Segoe UI"
FONT_SEMIBOLD = "Segoe UI Semibold"
ROW_HEIGHT = 36
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
ASSETS = Path(__file__).resolve().parent / "assets"
APP_USER_MODEL_ID = "DLSSUnlockedManager"  # own taskbar group, so Windows shows our icon, not python's


@dataclass(frozen=True)
class Palette:
    mode: str
    text: str
    muted: str
    ok: str
    warn: str
    danger: str
    surface: str


PALETTES = {
    "dark": Palette("dark", text="#ffffff", muted="#9d9d9d", ok="#6ccb5f",
                    warn="#fce100", danger="#ff99a4", surface="#2b2b2b"),
    "light": Palette("light", text="#1a1a1a", muted="#6e6e6e", ok="#0f7b0f",
                     warn="#9d5d00", danger="#c42b1c", surface="#f9f9f9"),
}


def system_theme() -> str:
    """'dark' or 'light', following the Windows app colour setting."""
    if sys.platform != "win32":
        return "light"
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except OSError:
        return "light"
    return "light" if value else "dark"


def resolve(theme: str) -> str:
    return system_theme() if theme == "system" else theme


def _paint_title_bar(window: tk.Misc, dark: bool) -> None:
    """Dark/light native title bar on Windows 10 20H1+ / 11; silently unsupported elsewhere."""
    if sys.platform != "win32":
        return
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        flag = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE,
                                                   ctypes.byref(flag), ctypes.sizeof(flag))
    except (OSError, AttributeError):
        pass  # older Windows: keep the default title bar


def apply_theme(root: tk.Tk, mode: str) -> Palette:
    sv_ttk.set_theme(mode, root)
    try:
        # sv_ttk recolours frames/labels on <<ThemeChanged>>, which does not always arrive;
        # run its colour procedure directly so the window never stays half-themed.
        root.tk.call("configure_colors")
    except tk.TclError:
        pass  # a future sv_ttk without this procedure handles colours itself
    palette = PALETTES[mode]
    style = ttk.Style(root)
    style.configure("Title.TLabel", font=(FONT_SEMIBOLD, 20))
    style.configure("Subtitle.TLabel", font=(FONT, 10), foreground=palette.muted)
    style.configure("Muted.TLabel", font=(FONT, 9), foreground=palette.muted)
    style.configure("Strong.TLabel", font=(FONT_SEMIBOLD, 11))
    style.configure("Ok.TLabel", font=(FONT, 9), foreground=palette.ok)
    style.configure("Warn.TLabel", font=(FONT, 9), foreground=palette.warn)
    style.configure("Placeholder.TEntry", foreground=palette.muted)
    style.configure("Treeview", rowheight=ROW_HEIGHT, font=(FONT, 10))
    style.configure("Treeview.Heading", font=(FONT_SEMIBOLD, 9))
    _paint_title_bar(root, mode == "dark")
    return palette


def set_app_icon(root: tk.Tk) -> None:
    """Window, dialog and taskbar icon; a missing asset just leaves the default Tk icon."""
    try:
        if sys.platform == "win32":
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
            root.iconbitmap(default=str(ASSETS / "icon.ico"))  # default= also covers dialogs
        else:
            root.iconphoto(True, tk.PhotoImage(master=root, file=str(ASSETS / "icon.png")))
    except (tk.TclError, OSError, AttributeError):
        pass


def paint_dialog(window: tk.Toplevel, mode: str) -> None:
    _paint_title_bar(window, mode == "dark")
