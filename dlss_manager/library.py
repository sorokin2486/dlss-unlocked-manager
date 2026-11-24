"""Glue between game discovery (Steam + user-added folders) and per-game scanning."""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import package
from .scanner import GameScan, Support, scan_game
from .steam import SteamGame, find_steam_dir, installed_games, library_dirs

LOG = logging.getLogger(__name__)
SCAN_WORKERS = 8
CUSTOM_ID_PREFIX = "folder:"
SUPPORT_LABELS = {
    Support.FULL: "Поддерживается",
    Support.UPSCALE_ONLY: "Только апскейл (нет FG)",
    Support.BLOCKED: "Античит — не трогать",
    Support.NONE: "Нет DLSS",
}


def custom_folders_file() -> Path:
    return package.APP_DIR / "custom_games.json"


def load_custom_folders() -> list[Path]:
    """Folders the user added by hand. A corrupt file is set aside, not silently reused."""
    path = custom_folders_file()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
            raise ValueError("expected a list of folder paths")
    except (OSError, ValueError) as err:
        LOG.warning("Ignoring unreadable %s: %s", path, err)
        path.replace(path.with_suffix(".bad.json"))
        return []
    return [Path(item) for item in data]


def _save_custom_folders(folders: list[Path]) -> None:
    path = custom_folders_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([str(f) for f in folders], ensure_ascii=False, indent=2), encoding="utf-8")


def _same(a: Path, b: Path) -> bool:
    return str(a.resolve()).lower() == str(b.resolve()).lower()


def add_custom_folder(folder: Path) -> list[Path]:
    if not folder.is_dir():
        raise FileNotFoundError(f"Папка не найдена: {folder}")
    current = load_custom_folders()
    updated = current if any(_same(f, folder) for f in current) else [*current, folder]
    _save_custom_folders(updated)
    return updated


def remove_custom_folder(folder: Path) -> list[Path]:
    updated = [f for f in load_custom_folders() if not _same(f, folder)]
    _save_custom_folders(updated)
    return updated


def custom_game(folder: Path) -> SteamGame:
    """Describe a hand-added folder as a game; the id keeps it distinct from Steam app ids."""
    pretty = folder.name.replace(".", " ").replace("_", " ").strip() or str(folder)
    return SteamGame(app_id=f"{CUSTOM_ID_PREFIX}{folder}", name=pretty, install_dir=folder)


def is_custom(scan: GameScan) -> bool:
    return scan.game.app_id.startswith(CUSTOM_ID_PREFIX)


def discover_games() -> list[SteamGame]:
    steam = installed_games(library_dirs(find_steam_dir()))
    custom = [custom_game(f) for f in load_custom_folders() if f.is_dir()]
    return [*steam, *custom]


def scan_library(games: list[SteamGame] | None = None) -> list[GameScan]:
    games = discover_games() if games is None else games
    with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as pool:
        return list(pool.map(scan_game, games))


def find_game(scans: list[GameScan], query: str) -> GameScan:
    """Match by exact app id, then by case-insensitive name substring."""
    by_id = [s for s in scans if s.game.app_id == query]
    if by_id:
        return by_id[0]
    matches = [s for s in scans if query.lower() in s.game.name.lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise LookupError(f"Игра не найдена: {query}")
    names = ", ".join(s.game.name for s in matches)
    raise LookupError(f"Несколько игр подходят под «{query}»: {names}")
