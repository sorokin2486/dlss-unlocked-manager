"""Small reusable widgets: search field with placeholder and the settings dialog."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..installer import MENU_KEYS, PROXY_NAMES
from ..settings import AUTO, Settings
from .theme import paint_dialog

THEME_LABELS = {"system": "Как в Windows", "dark": "Тёмная", "light": "Светлая"}
PROXY_AUTO_LABEL = "Автоматически"


class SearchEntry(ttk.Entry):
    """Entry that shows a muted placeholder while empty; `value` never returns the placeholder."""

    def __init__(self, master: tk.Misc, placeholder: str, on_change: Callable[[str], None]) -> None:
        self._var = tk.StringVar()
        super().__init__(master, textvariable=self._var)
        self._placeholder = placeholder
        self._showing = False
        self._on_change = on_change
        self.bind("<FocusIn>", lambda _e: self._hide())
        self.bind("<FocusOut>", lambda _e: self._show())
        self.bind("<Escape>", lambda _e: self.clear())
        self._var.trace_add("write", lambda *_: None if self._showing else on_change(self.value))
        self._show()

    @property
    def value(self) -> str:
        return "" if self._showing else self._var.get().strip()

    def clear(self) -> None:
        self._var.set("")
        self.master.focus_set()

    def _show(self) -> None:
        if not self._var.get():
            self._showing = True
            self._var.set(self._placeholder)
            self.configure(style="Placeholder.TEntry")

    def _hide(self) -> None:
        if self._showing:
            self._var.set("")
            self._showing = False
            self.configure(style="TEntry")


def ask_settings(root: tk.Tk, current: Settings, mode: str) -> Settings | None:
    """Modal settings dialog; returns new settings or None when cancelled."""
    dialog = tk.Toplevel(root)
    dialog.title("Параметры")
    dialog.transient(root)
    dialog.resizable(False, False)
    body = ttk.Frame(dialog, padding=24)
    body.pack(fill="both", expand=True)

    menu_key = tk.StringVar(value=current.menu_key)
    proxy = tk.StringVar(value=PROXY_AUTO_LABEL if current.proxy == AUTO else current.proxy)
    theme = tk.StringVar(value=THEME_LABELS[current.theme])
    rows = (
        ("Клавиша меню OptiScaler", menu_key, list(MENU_KEYS),
         "Открывает меню мода в игре. Insert есть не на всех клавиатурах."),
        ("Имя DLL мода", proxy, [PROXY_AUTO_LABEL, *PROXY_NAMES],
         "Автоматически — первое свободное имя (обычно dxgi)."),
        ("Тема", theme, list(THEME_LABELS.values()), ""),
    )
    for row, (label, var, values, hint) in enumerate(rows):
        ttk.Label(body, text=label, style="Strong.TLabel").grid(row=row * 2, column=0, sticky="w", pady=(0 if row == 0 else 14, 2))
        ttk.Combobox(body, textvariable=var, values=values, state="readonly", width=18).grid(
            row=row * 2, column=1, sticky="e", padx=(24, 0), pady=(0 if row == 0 else 14, 2))
        if hint:
            ttk.Label(body, text=hint, style="Muted.TLabel").grid(row=row * 2 + 1, column=0, columnspan=2, sticky="w")

    result: dict[str, Settings] = {}

    def save() -> None:
        theme_key = next(k for k, v in THEME_LABELS.items() if v == theme.get())
        result["value"] = Settings(
            menu_key=menu_key.get(),
            proxy=AUTO if proxy.get() == PROXY_AUTO_LABEL else proxy.get(),
            theme=theme_key,
        ).validated()
        dialog.destroy()

    buttons = ttk.Frame(body)
    buttons.grid(row=len(rows) * 2, column=0, columnspan=2, sticky="e", pady=(24, 0))
    ttk.Button(buttons, text="Отмена", command=dialog.destroy).pack(side="right")
    ttk.Button(buttons, text="Сохранить", style="Accent.TButton", command=save).pack(side="right", padx=(0, 8))
    dialog.bind("<Escape>", lambda _e: dialog.destroy())
    dialog.bind("<Return>", lambda _e: save())

    paint_dialog(dialog, mode)
    dialog.update_idletasks()
    x = root.winfo_rootx() + (root.winfo_width() - dialog.winfo_width()) // 2
    y = root.winfo_rooty() + (root.winfo_height() - dialog.winfo_height()) // 3
    dialog.geometry(f"+{x}+{y}")
    dialog.grab_set()
    root.wait_window(dialog)
    return result.get("value")
