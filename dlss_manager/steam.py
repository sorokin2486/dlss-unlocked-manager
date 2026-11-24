"""Steam library discovery: install path, library folders and installed games."""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_STEAM_DIR = Path(r"C:\Program Files (x86)\Steam")

# Steam tools and runtimes that show up as "apps" but are never games.
_NON_GAME_NAME = re.compile(
    r"^(proton|steam linux runtime|steamworks common redistributables|steamvr)",
    re.IGNORECASE,
)
_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')
_ESCAPE = re.compile(r"\\(.)")


@dataclass(frozen=True)
class SteamGame:
    app_id: str
    name: str
    install_dir: Path


class VdfError(ValueError):
    """Raised when a Valve KeyValues (.vdf / .acf) file cannot be parsed."""


def _unescape(value: str) -> str:
    return _ESCAPE.sub(r"\1", value)


def parse_vdf(text: str) -> dict:
    """Parse Valve's text KeyValues format into nested dicts of strings."""
    root: dict = {}
    stack = [root]
    key: str | None = None
    for match in _TOKEN.finditer(text):
        string, brace = match.group(1), match.group(2)
        if brace == "{":
            if key is None:
                raise VdfError("'{' without a key")
            child: dict = {}
            stack[-1][key] = child
            stack.append(child)
            key = None
        elif brace == "}":
            if len(stack) == 1:
                raise VdfError("unbalanced '}'")
            stack.pop()
            key = None
        elif key is None:
            key = _unescape(string)
        else:
            stack[-1][key] = _unescape(string)
            key = None
    if len(stack) != 1:
        raise VdfError("unclosed '{'")
    return root


def find_steam_dir() -> Path:
    """Locate the Steam client folder via the registry, falling back to the default path."""
    if sys.platform == "win32":
        import winreg

        lookups = (
            (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        )
        for hive, subkey, value_name in lookups:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
            except OSError:
                continue
            path = Path(value)
            if path.is_dir():
                return path
    return DEFAULT_STEAM_DIR


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path.resolve()).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def library_dirs(steam_dir: Path) -> list[Path]:
    """Return every Steam library folder (the ones holding a steamapps directory)."""
    candidates = [steam_dir]
    vdf_path = steam_dir / "steamapps" / "libraryfolders.vdf"
    if vdf_path.is_file():
        data = parse_vdf(vdf_path.read_text(encoding="utf-8", errors="replace"))
        folders = data.get("libraryfolders") or data.get("LibraryFolders") or {}
        for entry in folders.values():
            if isinstance(entry, dict) and "path" in entry:
                candidates.append(Path(entry["path"]))
            elif isinstance(entry, str) and entry and entry[0].isalpha() and ":" in entry:
                candidates.append(Path(entry))  # legacy format: "1" "D:\\Games"
    existing = [p for p in candidates if (p / "steamapps").is_dir()]
    return _dedupe_paths(existing)


def _read_manifest(acf_path: Path, library: Path) -> SteamGame | None:
    try:
        state = parse_vdf(acf_path.read_text(encoding="utf-8", errors="replace")).get("AppState", {})
    except (OSError, VdfError):
        return None
    app_id, name, folder = state.get("appid"), state.get("name"), state.get("installdir")
    if not (app_id and name and folder) or _NON_GAME_NAME.match(name):
        return None
    install_dir = library / "steamapps" / "common" / folder
    if not install_dir.is_dir():
        return None
    return SteamGame(app_id=app_id, name=name, install_dir=install_dir)


def installed_games(libraries: list[Path]) -> list[SteamGame]:
    """Read appmanifest_*.acf from each library and return installed games sorted by name."""
    games = [
        game
        for library in libraries
        for acf in sorted((library / "steamapps").glob("appmanifest_*.acf"))
        if (game := _read_manifest(acf, library)) is not None
    ]
    return sorted(games, key=lambda g: g.name.lower())
