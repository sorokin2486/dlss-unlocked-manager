"""Command line interface: scan / install / uninstall / download. No arguments opens the GUI."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import package
from .installer import MENU_KEYS, PROXY_NAMES, InstallError, install, set_menu_key, uninstall
from .library import SUPPORT_LABELS, custom_game, find_game, scan_library
from .scanner import GameScan, Support, scan_game

BYTES_PER_MB = 1024 * 1024


def _out(text: str = "") -> None:
    sys.stdout.write(text + "\n")


def _row(scan: GameScan) -> str:
    flags = "".join(
        mark if on else "-"
        for mark, on in (("S", scan.has_dlss_sr), ("G", scan.has_dlss_fg), ("X", scan.dx12_hint))
    )
    status = "[СѓСЃС‚Р°РЅРѕРІР»РµРЅ] " if scan.installed else ""
    ac = f" ({', '.join(scan.anti_cheat)})" if scan.anti_cheat else ""
    return f"{scan.game.app_id:>8}  {flags}  {status}{scan.game.name} вЂ” {SUPPORT_LABELS[scan.support]}{ac}"


def cmd_scan(args: argparse.Namespace) -> int:
    scans = scan_library()
    shown = scans if args.all else [s for s in scans if s.support is not Support.NONE]
    _out("Р¤Р»Р°РіРё: S = DLSS Р°РїСЃРєРµР№Р», G = РіРµРЅРµСЂР°С†РёСЏ РєР°РґСЂРѕРІ, X = РїСЂРёР·РЅР°РєРё DX12\n")
    for scan in shown:
        _out(_row(scan))
        if args.verbose and scan.main_exe:
            _out(f"{'':10}exe: {scan.main_exe}")
    supported = sum(s.support is Support.FULL for s in scans)
    _out(f"\nРРіСЂ РІСЃРµРіРѕ: {len(scans)}, СЃ DLSS: {len(shown) if not args.all else '-'}, РїРѕРґС…РѕРґСЏС‚: {supported}")
    return 0


def _package_dir(arg: str | None) -> Path:
    if arg:
        return package.resolve_package(Path(arg))
    local = package.newest_local_package()
    if local is None:
        raise InstallError("РџР°РєРµС‚ РјРѕРґР° РЅРµ РЅР°Р№РґРµРЅ. РЎРЅР°С‡Р°Р»Р°: download РёР»Рё --package РїСѓС‚СЊ_Рє_zip")
    return local


def _resolve_game(query: str) -> GameScan:
    """A folder path scans that folder directly (games outside Steam); otherwise search Steam."""
    folder = Path(query)
    if folder.is_absolute() and folder.is_dir():
        return scan_game(custom_game(folder))
    return find_game(scan_library(), query)


def cmd_install(args: argparse.Namespace) -> int:
    scan = _resolve_game(args.game)
    if scan.support is Support.BLOCKED and not args.force:
        raise InstallError(f"Р’ РёРіСЂРµ Р°РЅС‚РёС‡РёС‚ ({', '.join(scan.anti_cheat)}). РЈСЃС‚Р°РЅРѕРІРєР° РѕС‚РјРµРЅРµРЅР°.")
    if scan.support is Support.NONE and not args.force:
        raise InstallError("Р’ РёРіСЂРµ РЅРµС‚ DLSS вЂ” РјРѕРґ СЂР°Р±РѕС‚Р°С‚СЊ РЅРµ Р±СѓРґРµС‚.")
    if scan.exe_dir is None:
        raise InstallError("РќРµ СѓРґР°Р»РѕСЃСЊ РЅР°Р№С‚Рё exe РёРіСЂС‹")
    target = Path(args.target) if args.target else scan.exe_dir
    result = install(_package_dir(args.package), target, proxy=args.proxy,
                     repatch=args.repatch, reset_config=args.reset_config)
    _out(f"РЈСЃС‚Р°РЅРѕРІР»РµРЅРѕ РІ {result.game_dir} РєР°Рє {result.proxy}.dll ({len(result.files)} С„Р°Р№Р»РѕРІ)")
    if result.backed_up:
        _out(f"РЎРѕС…СЂР°РЅРµРЅС‹ СЂРµР·РµСЂРІРЅС‹Рµ РєРѕРїРёРё: {', '.join(result.backed_up)}")
    if result.kept_config:
        _out("Р’Р°С€ OptiScaler.ini РѕСЃС‚Р°РІР»РµРЅ Р±РµР· РёР·РјРµРЅРµРЅРёР№")
    if args.menu_key:
        set_menu_key(result.game_dir, args.menu_key)
    if scan.support is Support.UPSCALE_ONLY:
        _out("Р’РЅРёРјР°РЅРёРµ: РІ РёРіСЂРµ РЅРµС‚ РЅР°С‚РёРІРЅРѕР№ РіРµРЅРµСЂР°С†РёРё РєР°РґСЂРѕРІ вЂ” MFG РЅРµ РїРѕСЏРІРёС‚СЃСЏ.")
    key = args.menu_key or ("РїСЂРµР¶РЅСЏСЏ РєР»Р°РІРёС€Р°" if result.kept_config else "Insert")
    _out(f"РњРµРЅСЋ OptiScaler РІ РёРіСЂРµ: {key}.")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    scan = _resolve_game(args.game)
    target = Path(args.target) if args.target else scan.exe_dir
    if target is None:
        raise InstallError("РќРµ СѓРґР°Р»РѕСЃСЊ РЅР°Р№С‚Рё exe РёРіСЂС‹")
    removed = uninstall(target)
    _out(f"РЈРґР°Р»РµРЅРѕ {len(removed)} С„Р°Р№Р»РѕРІ РёР· {target}, РѕСЂРёРіРёРЅР°Р»СЊРЅС‹Рµ С„Р°Р№Р»С‹ РІРѕСЃСЃС‚Р°РЅРѕРІР»РµРЅС‹")
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    asset = package.latest_release_asset()
    _out(f"{asset.name} ({asset.tag}), {asset.size / BYTES_PER_MB:.0f} РњР‘\n{asset.url}")
    if not args.yes and input("РЎРєР°С‡Р°С‚СЊ? [y/N] ").strip().lower() not in {"y", "Рґ", "yes", "РґР°"}:
        _out("РћС‚РјРµРЅРµРЅРѕ")
        return 1

    def progress(done: int, total: int) -> None:
        sys.stdout.write(f"\r{done / BYTES_PER_MB:.0f} / {total / BYTES_PER_MB:.0f} РњР‘")
        sys.stdout.flush()

    zip_path = package.download(asset, progress)
    _out(f"\nР Р°СЃРїР°РєРѕРІРєР° {zip_path.name}вЂ¦")
    _out(f"Р“РѕС‚РѕРІРѕ: {package.extract_package(zip_path)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dlss_manager", description="РњРµРЅРµРґР¶РµСЂ DLSS Unlocked РґР»СЏ Steam")
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="РЅР°Р№С‚Рё РёРіСЂС‹ СЃ DLSS")
    scan.add_argument("--all", action="store_true", help="РїРѕРєР°Р·Р°С‚СЊ Рё РёРіСЂС‹ Р±РµР· DLSS")
    scan.add_argument("-v", "--verbose", action="store_true", help="РїРѕРєР°Р·Р°С‚СЊ РїСѓС‚СЊ Рє exe")
    scan.set_defaults(func=cmd_scan)

    for name, func, text in (("install", cmd_install, "СѓСЃС‚Р°РЅРѕРІРёС‚СЊ РјРѕРґ"),
                             ("uninstall", cmd_uninstall, "СѓРґР°Р»РёС‚СЊ РјРѕРґ")):
        p = sub.add_parser(name, help=text)
        p.add_argument("game", help="AppID, С‡Р°СЃС‚СЊ РЅР°Р·РІР°РЅРёСЏ РёР»Рё РїРѕР»РЅС‹Р№ РїСѓС‚СЊ Рє РїР°РїРєРµ РёРіСЂС‹ (РЅРµ РёР· Steam)")
        p.add_argument("--target", help="РїР°РїРєР° exe РІСЂСѓС‡РЅСѓСЋ (РµСЃР»Рё РѕРїСЂРµРґРµР»РёР»Р°СЃСЊ РЅРµРІРµСЂРЅРѕ)")
        p.set_defaults(func=func)
        if name == "install":
            p.add_argument("--package", help="zip РёР»Рё СЂР°СЃРїР°РєРѕРІР°РЅРЅР°СЏ РїР°РїРєР° РјРѕРґР°")
            p.add_argument("--proxy", choices=PROXY_NAMES, help="РёРјСЏ DLL (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ вЂ” РїРµСЂРІРѕРµ СЃРІРѕР±РѕРґРЅРѕРµ)")
            p.add_argument("--repatch", action="store_true", help="REFramework РґР»СЏ РёРіСЂ РЅР° RE Engine")
            p.add_argument("--reset-config", action="store_true", help="РїРµСЂРµР·Р°РїРёСЃР°С‚СЊ OptiScaler.ini")
            p.add_argument("--force", action="store_true", help="СЃС‚Р°РІРёС‚СЊ РґР°Р¶Рµ Р±РµР· DLSS / СЃ Р°РЅС‚РёС‡РёС‚РѕРј")
            p.add_argument("--menu-key", choices=list(MENU_KEYS), help="РєР»Р°РІРёС€Р° РјРµРЅСЋ OptiScaler (РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ Insert)")

    dl = sub.add_parser("download", help="СЃРєР°С‡Р°С‚СЊ РїРѕСЃР»РµРґРЅРёР№ СЂРµР»РёР· СЃ GitHub")
    dl.add_argument("-y", "--yes", action="store_true", help="РЅРµ СЃРїСЂР°С€РёРІР°С‚СЊ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёРµ")
    dl.set_defaults(func=cmd_download)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command is None:
        from .ui.app import run_gui

        run_gui()
        return 0
    try:
        return args.func(args)
    except (InstallError, LookupError) as err:
        sys.stderr.write(f"РћС€РёР±РєР°: {err}\n")
        return 2
