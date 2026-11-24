"""Inspect a game folder: DLSS / frame generation DLLs, main executable, anti-cheat."""
from __future__ import annotations

import mmap
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .installer import MANIFEST_NAME
from .steam import SteamGame

MAX_DEPTH = 10  # UE: <Game>/Engine/Plugins/Runtime/Nvidia/DLSS/Binaries/ThirdParty/Win64
DLSS_SR_FILES = frozenset({"nvngx_dlss.dll"})
DLSS_FG_FILES = frozenset({"nvngx_dlssg.dll", "sl.dlss_g.dll"})
STREAMLINE_FILES = frozenset({"sl.interposer.dll"})
RE_ENGINE_MARKER = "re_chunk_000.pak"  # every Capcom RE Engine game ships this archive
ANTI_CHEAT_DIRS = {"easyanticheat": "EasyAntiCheat", "battleye": "BattlEye"}
ANTI_CHEAT_FILES = {
    "easyanticheat_x64.dll": "EasyAntiCheat",
    "easyanticheat_eos_setup.exe": "EasyAntiCheat",
    "start_protected_game.exe": "EasyAntiCheat",
    "beclient_x64.dll": "BattlEye",
    "beservice_x64.exe": "BattlEye",
    "mhyprot2.sys": "mhyprot",
}
# Any file or folder named like this means an anti-cheat ships with the game.
ANTI_CHEAT_NAME = re.compile(r"anti[-_ ]?cheat", re.IGNORECASE)
# Online games whose anti-cheat leaves no trace in the game folder (server-side, VAC,
# NetEase/Tencent ACE, launcher-installed). Injecting DLLs into them risks a ban.
KNOWN_ONLINE_APPS = {
    "730": "VAC", "570": "VAC", "1422450": "VAC",            # CS2, Dota 2, Deadlock
    "2767030": "NetEase ACE",                                 # Marvel Rivals
    "2073850": "EAC", "1808500": "EAC",                       # THE FINALS, ARC Raiders
    "1172470": "EAC", "381210": "EAC", "1203220": "NetEase",  # Apex, Dead by Daylight, Naraka
    "578080": "BattlEye", "252490": "EAC", "359550": "BattlEye",  # PUBG, Rust, R6 Siege
    "2357570": "Defense Matrix", "1085660": "BattlEye",       # Overwatch 2, Destiny 2
    "1938090": "Ricochet", "2807960": "Javelin",              # Call of Duty, Battlefield 6
    "2507950": "ACE", "2074920": "EAC", "594650": "EAC",      # Delta Force, First Descendant, Hunt
    "230410": "Warframe", "236390": "EAC", "393380": "EAC",   # Warframe, War Thunder, Squad
    "271590": "BattlEye", "3240220": "BattlEye",              # GTA V (legacy / enhanced)
}
SKIP_DIRS = frozenset({"_commonredist", "commonredist", "redist", "__installer", "directx", "vcredist"})
JUNK_EXE = re.compile(
    r"unins|crash|redist|setup|report|prereq|vc_?redist|dxsetup|helper|anti.?cheat|"
    r"beservice|battleye|launcher|cefprocess|uploader|dotnet|python|7z|start_protected|"
    r"vconsole|diagnose|capture|webview|qtwebengine|installer|benchmark|tool",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9]")
NAME_MATCH_MIN = 4
_D3D12 = re.compile(rb"d3d12(core)?\.dll", re.IGNORECASE)
_BYTES_PER_MB = 1024 * 1024


class Support(str, Enum):
    FULL = "full"            # DLSS upscaling + native frame generation: the mod applies
    UPSCALE_ONLY = "upscale"  # DLSS upscaling only: the mod's FG/MFG will not unlock
    BLOCKED = "anticheat"     # supported DLLs, but anti-cheat present: do not touch
    NONE = "none"             # no DLSS in the game


@dataclass(frozen=True)
class GameScan:
    game: SteamGame
    main_exe: Path | None
    has_dlss_sr: bool
    has_dlss_fg: bool
    has_streamline: bool
    dx12_hint: bool
    anti_cheat: tuple[str, ...]
    installed: bool
    re_engine: bool = False  # Capcom RE Engine: REFramework is recommended alongside the mod

    @property
    def exe_dir(self) -> Path | None:
        return self.main_exe.parent if self.main_exe else None

    @property
    def support(self) -> Support:
        if not self.has_dlss_sr:
            return Support.NONE
        if self.anti_cheat:
            return Support.BLOCKED
        return Support.FULL if self.has_dlss_fg else Support.UPSCALE_ONLY


@dataclass(frozen=True)
class _Inventory:
    files: dict[str, tuple[Path, ...]]  # lower-case file name -> every location
    exes: tuple[Path, ...]
    anti_cheat: tuple[str, ...]


def _walk(root: Path) -> _Inventory:
    files: dict[str, list[Path]] = {}
    exes: list[Path] = []
    anti_cheat: set[str] = set()
    root_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _err: None):
        here = Path(dirpath)
        for name in dirnames:
            if name.lower() in ANTI_CHEAT_DIRS:
                anti_cheat.add(ANTI_CHEAT_DIRS[name.lower()])
            elif ANTI_CHEAT_NAME.search(name):
                anti_cheat.add("Anti-cheat")
        if len(here.parts) - root_depth >= MAX_DEPTH:
            dirnames[:] = []
        else:
            # "_..." folders hold redists, installers or backup copies of the game files.
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS and not d.startswith("_")]
        for name in filenames:
            lower = name.lower()
            files.setdefault(lower, []).append(here / name)
            if lower in ANTI_CHEAT_FILES:
                anti_cheat.add(ANTI_CHEAT_FILES[lower])
            elif ANTI_CHEAT_NAME.search(name):
                anti_cheat.add("Anti-cheat")
            if lower.endswith(".exe"):
                exes.append(here / name)
    return _Inventory(
        files={k: tuple(v) for k, v in files.items()},
        exes=tuple(exes),
        anti_cheat=tuple(sorted(anti_cheat)),
    )


def _size_mb(path: Path) -> float:
    try:
        return path.stat().st_size / _BYTES_PER_MB
    except OSError:
        return 0.0


def _alnum(text: str) -> str:
    return _NON_ALNUM.sub("", text.lower())


def _matches_game_name(exe: Path, game_names: tuple[str, ...]) -> bool:
    stem = _alnum(exe.stem)
    return len(stem) >= NAME_MATCH_MIN and any(
        len(name) >= NAME_MATCH_MIN and (stem in name or name in stem) for name in game_names
    )


def pick_main_exe(
    exes: tuple[Path, ...], dll_dirs: frozenset[Path], game_names: tuple[str, ...] = ()
) -> Path | None:
    """Choose the game's real executable: skip helpers, prefer UE '-Shipping', DLSS folders
    and an exe named after the game; size only breaks ties."""
    candidates = [e for e in exes if not JUNK_EXE.search(e.name)] or list(exes)
    if not candidates:
        return None
    names = tuple(_alnum(n) for n in game_names)

    def score(exe: Path) -> float:
        bonus = 0.0
        if exe.parent in dll_dirs:
            bonus += 100
        if "shipping" in exe.name.lower():
            bonus += 80
        if _matches_game_name(exe, names):
            bonus += 60
        return bonus + min(_size_mb(exe), 50)

    return max(candidates, key=score)


def mentions_d3d12(exe: Path) -> bool:
    """Best-effort DX12 hint: the executable references d3d12.dll or D3D12Core.dll."""
    try:
        with exe.open("rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as data:
            return _D3D12.search(data) is not None
    except (OSError, ValueError):
        return False


def scan_game(game: SteamGame) -> GameScan:
    inventory = _walk(game.install_dir)

    def present(names: frozenset[str]) -> tuple[Path, ...]:
        return tuple(p for n in names for p in inventory.files.get(n, ()))

    sr, fg, sl = present(DLSS_SR_FILES), present(DLSS_FG_FILES), present(STREAMLINE_FILES)
    dll_dirs = frozenset(p.parent for p in (*sr, *fg, *sl))
    main_exe = pick_main_exe(inventory.exes, dll_dirs, (game.name, game.install_dir.name))
    dx12 = bool(sl or fg or (main_exe and mentions_d3d12(main_exe)) or present(frozenset({"d3d12core.dll"})))
    installed = bool(main_exe and (main_exe.parent / MANIFEST_NAME).is_file())
    anti_cheat = set(inventory.anti_cheat)
    if game.app_id in KNOWN_ONLINE_APPS:
        anti_cheat.add(KNOWN_ONLINE_APPS[game.app_id])
    return GameScan(
        game=game,
        main_exe=main_exe,
        has_dlss_sr=bool(sr),
        has_dlss_fg=bool(fg),
        has_streamline=bool(sl),
        dx12_hint=dx12,
        anti_cheat=tuple(sorted(anti_cheat)),
        installed=installed,
        re_engine=RE_ENGINE_MARKER in inventory.files,
    )
