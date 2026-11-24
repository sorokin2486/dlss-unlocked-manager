"""Build 'DLSS Manager.exe' (single file, no console window) with PyInstaller.

Run:  python build_exe.py
The icon lives in dlss_manager/ui/assets; redraw it with  python tools/make_icon.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "dlss_manager" / "ui" / "assets"


def main() -> None:
    PyInstaller.__main__.run([
        str(ROOT / "DLSS Manager.pyw"),
        "--name", "DLSS Manager",
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--paths", str(ROOT),
        "--collect-data", "sv_ttk",  # Sun Valley theme: .tcl files and sprite sheets
        "--add-data", f"{ASSETS}{os.pathsep}dlss_manager/ui/assets",  # window / taskbar icon
        "--icon", str(ASSETS / "icon.ico"),
        "--distpath", str(ROOT),
        "--workpath", str(ROOT / "build" / "work"),
        "--specpath", str(ROOT / "build"),
    ])


if __name__ == "__main__":
    sys.exit(main())
