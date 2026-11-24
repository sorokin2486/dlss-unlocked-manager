"""Main window: games with DLSS (Steam + added folders), one-click install and removal."""
from __future__ import annotations

import os
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from .. import package
from ..installer import InstallError, install, set_menu_key, uninstall
from ..library import add_custom_folder, custom_game, is_custom, remove_custom_folder, scan_library
from ..scanner import GameScan, Support, scan_game
from ..settings import AUTO, Settings, load_settings, save_settings
from .theme import Palette, apply_theme, resolve, set_app_icon
from .widgets import SearchEntry, ask_settings

APP_TITLE = "DLSS Unlocked Manager"
SUBTITLE = "Генерация кадров и DLSS 5 для RTX 20 / 30 / 40"
BYTES_PER_MB = 1024 * 1024
FILTER_DLSS, FILTER_ALL = "dlss", "all"
ORDER = (Support.FULL, Support.UPSCALE_ONLY, Support.BLOCKED, Support.NONE)
STATUS_TEXT = {
    Support.FULL: "✓  Поддерживается",
    Support.UPSCALE_ONLY: "◐  Только апскейл",
    Support.BLOCKED: "⛔  Античит",
    Support.NONE: "—  Нет DLSS",
}
COLUMNS = (("name", "Игра", 320, True), ("status", "Статус", 200, False),
           ("mod", "Мод", 130, False), ("path", "Папка", 380, True))
_VERSION = re.compile(r"standalone-(.+)$", re.IGNORECASE)


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.settings: Settings = load_settings()
        self.palette: Palette = apply_theme(root, resolve(self.settings.theme))
        self.scans: dict[str, GameScan] = {}
        self.busy = False  # one background operation at a time: installs must never overlap
        self.critical = False  # the running operation writes files and must not be cut off by closing
        self.scanned_once = False
        self.package_dir: Path | None = package.newest_local_package()
        self.filter = tk.StringVar(value=FILTER_DLSS)
        self.status = tk.StringVar()
        self._build()
        self._apply_palette()
        self._refresh_package()
        self._update_actions()
        self.rescan()

    # ---- layout ---------------------------------------------------------------
    def _build(self) -> None:
        self.root.title(APP_TITLE)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.geometry("1180x700")
        self.root.minsize(920, 520)
        outer = ttk.Frame(self.root, padding=(28, 22, 28, 14))
        outer.pack(fill="both", expand=True)
        self._build_header(outer)
        self._build_toolbar(outer)
        self._build_table(outer)
        self._build_actions(outer)
        self._build_footer(outer)

    def _build_header(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent)
        header.pack(fill="x")
        titles = ttk.Frame(header)
        titles.pack(side="left")
        ttk.Label(titles, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(titles, text=SUBTITLE, style="Subtitle.TLabel").pack(anchor="w")

        right = ttk.Frame(header)
        right.pack(side="right")
        menu_button = ttk.Menubutton(right, text="⋯", width=2)
        menu = tk.Menu(menu_button, tearoff=False)
        menu.add_command(label="Параметры…", command=self.open_settings)
        menu.add_command(label="Выбрать zip мода вручную…", command=self.pick_package)
        menu.add_command(label="Открыть папку с данными", command=lambda: self._open(package.APP_DIR))
        menu_button["menu"] = menu
        menu_button.pack(side="right")
        self.package_button = ttk.Button(right, command=self.download)
        self.package_button.pack(side="right", padx=8)
        self.package_label = ttk.Label(right, style="Muted.TLabel")
        self.package_label.pack(side="right", padx=4)

    def _build_toolbar(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(20, 12))
        self.search = SearchEntry(bar, "Поиск игры…", lambda _value: self._render())
        self.search.pack(side="left", ipadx=70)
        for value, text in ((FILTER_DLSS, "С DLSS"), (FILTER_ALL, "Все игры")):
            ttk.Radiobutton(bar, text=text, value=value, variable=self.filter, style="Toggle.TButton",
                            command=self._render).pack(side="left", padx=(10 if value == FILTER_DLSS else 4, 0))
        ttk.Button(bar, text="＋  Добавить папку", command=self.add_folder).pack(side="right")
        ttk.Button(bar, text="⟳  Обновить", command=self.rescan).pack(side="right", padx=8)

    def _build_table(self, parent: ttk.Frame) -> None:
        card = ttk.Frame(parent)
        card.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(card, columns=[c[0] for c in COLUMNS], show="headings", selectmode="browse")
        for key, title, width, stretch in COLUMNS:
            self.tree.heading(key, text=title, anchor="w")
            self.tree.column(key, width=width, stretch=stretch, anchor="w")
        scroll = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.empty = ttk.Label(card, style="Subtitle.TLabel")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_actions())
        self.tree.bind("<Double-1>", lambda _e: self.install_selected())
        self.tree.bind("<Button-3>", self._context_menu)

    def _build_actions(self, parent: ttk.Frame) -> None:
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(14, 0))
        info = ttk.Frame(bar)
        info.pack(side="left", fill="x", expand=True)
        self.sel_title = ttk.Label(info, style="Strong.TLabel")
        self.sel_title.pack(anchor="w")
        self.sel_detail = ttk.Label(info, style="Muted.TLabel")
        self.sel_detail.pack(anchor="w")
        self.install_btn = ttk.Button(bar, text="Установить", style="Accent.TButton", width=16,
                                      command=self.install_selected)
        self.install_btn.pack(side="right")
        self.uninstall_btn = ttk.Button(bar, text="Удалить мод", command=self.uninstall_selected)
        self.uninstall_btn.pack(side="right", padx=8)
        self.folder_btn = ttk.Button(bar, text="Открыть папку", command=self.open_folder)
        self.folder_btn.pack(side="right")
        self.remove_btn = ttk.Button(bar, text="Убрать из списка", command=self.remove_folder)
        self.remove_btn.pack(side="right", padx=8)

    def _build_footer(self, parent: ttk.Frame) -> None:
        footer = ttk.Frame(parent)
        footer.pack(fill="x", pady=(12, 0))
        ttk.Label(footer, textvariable=self.status, style="Muted.TLabel").pack(side="left")
        self.progress = ttk.Progressbar(footer, length=180)

    def _apply_palette(self) -> None:
        self.tree.tag_configure("blocked", foreground=self.palette.danger)
        self.tree.tag_configure("none", foreground=self.palette.muted)

    # ---- state ----------------------------------------------------------------
    def _selected(self) -> GameScan | None:
        selection = self.tree.selection()
        return self.scans.get(selection[0]) if selection else None

    def _describe(self, scan: GameScan) -> str:
        parts = [str(scan.exe_dir) if scan.exe_dir else "exe игры не найден"]
        if scan.anti_cheat:
            parts.append(f"античит: {', '.join(scan.anti_cheat)} — установка заблокирована")
        elif scan.support is Support.UPSCALE_ONLY:
            parts.append("нет встроенной генерации кадров — MFG не появится")
        if scan.re_engine:
            parts.append("RE Engine — понадобится REFramework")
        return "   ·   ".join(parts)

    def _update_actions(self) -> None:
        scan = self._selected()
        idle = "disabled" if self.busy else "normal"
        if scan is None:
            self.sel_title.configure(text="Выберите игру")
            self.sel_detail.configure(text="Двойной щелчок по игре — установить мод")
            for button in (self.install_btn, self.uninstall_btn, self.folder_btn, self.remove_btn):
                button.state(["disabled"])
            return
        self.sel_title.configure(text=scan.game.name)
        self.sel_detail.configure(text=self._describe(scan))
        can_install = idle == "normal" and scan.exe_dir is not None and scan.support is not Support.BLOCKED
        self.install_btn.configure(text="Переустановить" if scan.installed else "Установить")
        self.install_btn.state(["!disabled"] if can_install else ["disabled"])
        self.uninstall_btn.state(["!disabled"] if scan.installed and not self.busy else ["disabled"])
        self.folder_btn.state(["!disabled"] if scan.exe_dir else ["disabled"])
        self.remove_btn.state(["!disabled"] if is_custom(scan) and not self.busy else ["disabled"])

    def _refresh_package(self) -> None:
        if self.package_dir is None:
            self.package_label.configure(text="Мод не скачан")
            self.package_button.configure(text="Скачать мод", style="Accent.TButton")
            return
        names = (self.package_dir.name, self.package_dir.parent.name)
        version = next((m.group(1) for n in names if (m := _VERSION.search(n))), self.package_dir.name)
        self.package_label.configure(text=f"Мод {version}")
        self.package_button.configure(text="Проверить обновление", style="TButton")

    def _render(self) -> None:
        keep = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        query = self.search.value.lower()
        rows = sorted(self.scans.values(), key=lambda s: (ORDER.index(s.support), s.game.name.lower()))
        shown = 0
        for scan in rows:
            custom = is_custom(scan)
            if self.filter.get() == FILTER_DLSS and scan.support is Support.NONE and not custom:
                continue
            if query and query not in scan.game.name.lower():
                continue
            status = STATUS_TEXT[scan.support]
            if scan.anti_cheat:
                status += f" ({', '.join(scan.anti_cheat)})"
            name = f"{scan.game.name}   · папка" if custom else scan.game.name
            values = (name, status, "●  Установлен" if scan.installed else "", str(scan.exe_dir or "—"))
            tag = {Support.BLOCKED: "blocked", Support.NONE: "none"}.get(scan.support, "")
            self.tree.insert("", "end", iid=scan.game.app_id, values=values, tags=(tag,))
            shown += 1
        if keep and self.tree.exists(keep[0]):
            self.tree.selection_set(keep[0])
        self._show_empty(shown)
        ready = sum(s.support is Support.FULL for s in self.scans.values())
        installed = sum(s.installed for s in self.scans.values())
        if not self.busy:
            self.status.set(f"Игр: {len(self.scans)}   ·   подходят: {ready}   ·   с модом: {installed}")
        self._update_actions()

    def _show_empty(self, shown: int) -> None:
        if shown:
            self.empty.place_forget()
            return
        text = "Ищу игры…" if not self.scanned_once else (
            "Ничего не найдено" if self.search.value else "Игр с DLSS не найдено — добавьте папку вручную")
        self.empty.configure(text=text)
        self.empty.place(relx=0.5, rely=0.45, anchor="center")

    def _select(self, app_id: str) -> None:
        if self.tree.exists(app_id):
            self.tree.selection_set(app_id)
            self.tree.see(app_id)

    # ---- background work ------------------------------------------------------
    def _run(self, label: str, work: Callable[[], object], done: Callable[[object], None],
             determinate: bool = False, critical: bool = False) -> None:
        if self.busy:
            return
        self.busy = True
        self.critical = critical
        self.status.set(label)
        self.progress.configure(mode="determinate" if determinate else "indeterminate", value=0)
        self.progress.pack(side="right")
        if not determinate:
            self.progress.start(12)
        self._update_actions()

        def target() -> None:
            try:
                result = work()
            except Exception as err:  # every failure is shown to the user, never swallowed
                self.root.after(0, self._finish, None, err)
                return
            self.root.after(0, self._finish, lambda: done(result), None)

        threading.Thread(target=target, daemon=True).start()

    def _finish(self, then: Callable[[], None] | None, err: Exception | None) -> None:
        self.busy = False
        self.critical = False
        self.progress.stop()
        self.progress.pack_forget()
        self.status.set("")
        self._render()
        if err is not None:
            messagebox.showerror("Ошибка", str(err), parent=self.root)
        elif then is not None:
            then()

    def _set_progress(self, done: int, total: int) -> None:
        self.progress.configure(maximum=max(total, 1), value=done)
        self.status.set(f"Загрузка мода: {done / BYTES_PER_MB:.0f} из {total / BYTES_PER_MB:.0f} МБ")

    # ---- actions --------------------------------------------------------------
    def rescan(self) -> None:
        def done(result: object) -> None:
            self.scans = {s.game.app_id: s for s in result}  # type: ignore[union-attr]
            self.scanned_once = True
            self._render()
        self._run("Ищу игры в Steam и добавленных папках…", scan_library, done)

    def _refresh_one(self, app_id: str) -> None:
        game = self.scans[app_id].game

        def done(result: object) -> None:
            self.scans = {**self.scans, app_id: result}  # type: ignore[dict-item]
            self._render()
            self._select(app_id)
        self._run("Обновляю статус…", lambda: scan_game(game), done)

    def add_folder(self) -> None:
        path = filedialog.askdirectory(title="Папка с игрой", mustexist=True, parent=self.root)
        if not path:
            return
        folder = Path(path)

        def work() -> GameScan:
            add_custom_folder(folder)
            return scan_game(custom_game(folder))

        def done(result: object) -> None:
            scan: GameScan = result  # type: ignore[assignment]
            self.scans = {**self.scans, scan.game.app_id: scan}
            self.search.clear()
            self._render()
            self._select(scan.game.app_id)
        self._run("Проверяю папку…", work, done)

    def remove_folder(self) -> None:
        scan = self._selected()
        if scan is None or not is_custom(scan):
            return
        if scan.installed:
            messagebox.showwarning(scan.game.name, "Сначала удалите мод из этой игры.", parent=self.root)
            return
        try:
            remove_custom_folder(scan.game.install_dir)
        except OSError as err:
            messagebox.showerror("Ошибка", f"Не удалось сохранить список папок: {err}", parent=self.root)
            return
        self.scans = {k: v for k, v in self.scans.items() if k != scan.game.app_id}
        self._render()

    def install_selected(self) -> None:
        scan = self._selected()
        if scan is None or self.busy or scan.exe_dir is None or scan.support is Support.BLOCKED:
            return
        if self.package_dir is None:
            if messagebox.askyesno("Мод не скачан", "Сначала нужно скачать мод. Скачать сейчас?", parent=self.root):
                self.download()
            return
        warning = {
            Support.NONE: "В игре не найден DLSS — мод, скорее всего, не заработает.\n\n",
            Support.UPSCALE_ONLY: "В игре нет встроенной генерации кадров — MFG не появится.\n\n",
        }.get(scan.support, "")
        if not messagebox.askyesno(scan.game.name, f"{warning}Установить DLSS Unlocked в\n{scan.exe_dir}?",
                                   parent=self.root):
            return
        repatch = scan.re_engine and messagebox.askyesno(
            "REFramework", "Это игра на RE Engine (Capcom). Без REFramework она может вылетать при запуске.\n\n"
                           "Установить REFramework вместе с модом? (рекомендуется)", parent=self.root)
        package_dir, exe_dir, app_id = self.package_dir, scan.exe_dir, scan.game.app_id
        proxy = None if self.settings.proxy == AUTO else self.settings.proxy
        menu_key = self.settings.menu_key

        def work() -> object:
            result = install(package_dir, exe_dir, proxy=proxy, repatch=repatch)
            set_menu_key(exe_dir, menu_key)
            return result

        def done(result: object) -> None:
            messagebox.showinfo("Готово", f"Мод установлен ({result.proxy}.dll).\n\n"  # type: ignore[union-attr]
                                f"В игре нажмите {menu_key} — откроется меню OptiScaler.", parent=self.root)
            self._refresh_one(app_id)
        self._run("Устанавливаю мод…", work, done, critical=True)

    def uninstall_selected(self) -> None:
        scan = self._selected()
        if scan is None or not scan.installed or scan.exe_dir is None or self.busy:
            return
        if not messagebox.askyesno(scan.game.name, "Удалить мод? Исходные файлы игры будут восстановлены.",
                                   parent=self.root):
            return
        exe_dir, app_id = scan.exe_dir, scan.game.app_id
        self._run("Удаляю мод…", lambda: uninstall(exe_dir), lambda _r: self._refresh_one(app_id), critical=True)

    def open_folder(self) -> None:
        scan = self._selected()
        if scan and scan.exe_dir:
            self._open(scan.exe_dir)

    def _open(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)  # noqa: S606 — opens Explorer on a local folder

    def _context_menu(self, event: tk.Event) -> None:
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.tree.selection_set(row)
        scan = self.scans[row]
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="Переустановить" if scan.installed else "Установить", command=self.install_selected,
                         state="normal" if str(self.install_btn["state"]) != "disabled" else "disabled")
        if scan.installed:
            menu.add_command(label="Удалить мод", command=self.uninstall_selected)
        menu.add_command(label="Открыть папку", command=self.open_folder)
        if is_custom(scan):
            menu.add_separator()
            menu.add_command(label="Убрать из списка", command=self.remove_folder)
        menu.tk_popup(event.x_root, event.y_root)

    def pick_package(self) -> None:
        path = filedialog.askopenfilename(title="Архив DLSS Unlocked (standalone .zip)",
                                          filetypes=[("ZIP", "*.zip")], parent=self.root)
        if path:
            self._run("Распаковываю…", lambda: package.resolve_package(Path(path)), self._package_ready,
                      critical=True)

    def _package_ready(self, result: object) -> None:
        self.package_dir = result  # type: ignore[assignment]
        self._refresh_package()

    def download(self) -> None:
        def confirm(asset: object) -> None:
            info: package.ReleaseAsset = asset  # type: ignore[assignment]
            if self.package_dir and Path(info.name).stem in (self.package_dir.name, self.package_dir.parent.name):
                messagebox.showinfo("Обновлений нет", f"У вас последняя версия мода ({info.tag}).", parent=self.root)
                return
            if messagebox.askyesno("Загрузка мода", f"Скачать DLSS Unlocked {info.tag}?\n\n"
                                   f"{info.size / BYTES_PER_MB:.0f} МБ с github.com/{package.REPO}",
                                   parent=self.root):
                self._download(info)
        self._run("Проверяю последнюю версию…", package.latest_release_asset, confirm)

    def _download(self, asset: package.ReleaseAsset) -> None:
        def progress(done: int, total: int) -> None:
            self.root.after(0, self._set_progress, done, total)

        def done(result: object) -> None:
            self._package_ready(result)
            messagebox.showinfo("Готово", f"Мод {asset.tag} скачан.", parent=self.root)
        self._run("Загрузка мода…", lambda: package.extract_package(package.download(asset, progress)),
                  done, determinate=True, critical=True)

    def close(self) -> None:
        if self.critical:
            messagebox.showinfo("Подождите", f"{self.status.get()}\n\nОкно можно будет закрыть, "
                                "когда операция закончится.", parent=self.root)
            return
        self.root.destroy()

    def open_settings(self) -> None:
        updated = ask_settings(self.root, self.settings, self.palette.mode)
        if updated is None or updated == self.settings:
            return
        try:
            save_settings(updated)
        except OSError as err:
            messagebox.showerror("Ошибка", f"Не удалось сохранить параметры: {err}", parent=self.root)
            return
        theme_changed = updated.theme != self.settings.theme
        self.settings = updated
        if theme_changed:
            self.palette = apply_theme(self.root, resolve(updated.theme))
            self._apply_palette()
            self._refresh_package()


def run_gui() -> None:
    root = tk.Tk()
    set_app_icon(root)
    try:
        App(root)
    except InstallError as err:
        messagebox.showerror("Ошибка", str(err))
    root.mainloop()
    # The window is closed and no file-writing operation is running (App.close waits for those).
    # Exit now instead of letting interpreter shutdown wait for a read-only game scan to finish.
    os._exit(0)
