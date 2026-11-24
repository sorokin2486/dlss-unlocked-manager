from pathlib import Path

from dlss_manager.cli import main
from dlss_manager.installer import MANIFEST_NAME


def _write(path: Path, data: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")


def _package(root: Path) -> Path:
    _write(root / "dxgi.dll", "optiscaler")
    (root / "OptiScaler.ini").write_bytes(b"[Menu]\r\nShortcutKey=auto\r\nShortcutKeyRequireCtrl=auto\r\n")
    _write(root / "OptiScaler" / "a.dll")
    return root


def test_install_by_folder_path_with_menu_key(tmp_path):
    package = _package(tmp_path / "pkg")
    game = tmp_path / "Some.Game"
    exe_dir = game / "platform" / "steam"
    _write(exe_dir / "Game.exe", "x" * 4000)
    _write(game / "_backup" / "platform" / "steam" / "Game.exe", "x" * 9000)  # ignored copy
    _write(game / "Engine" / "Plugins" / "DLSS" / "nvngx_dlss.dll")
    _write(game / "Engine" / "Plugins" / "SL" / "sl.dlss_g.dll")

    code = main(["install", str(game), "--package", str(package), "--menu-key", "F8"])

    assert code == 0
    assert (exe_dir / MANIFEST_NAME).is_file()
    assert (exe_dir / "dxgi.dll").read_text() == "optiscaler"
    ini = (exe_dir / "OptiScaler.ini").read_bytes()
    assert ini == b"[Menu]\r\nShortcutKey=0x77\r\nShortcutKeyRequireCtrl=auto\r\n"

    assert main(["uninstall", str(game)]) == 0
    assert not (exe_dir / "dxgi.dll").exists()
    assert (exe_dir / "Game.exe").exists()


def test_folder_without_dlss_is_refused(tmp_path):
    package = _package(tmp_path / "pkg")
    game = tmp_path / "NoDlss"
    _write(game / "Game.exe")

    assert main(["install", str(game), "--package", str(package)]) == 2
    assert not (game / "dxgi.dll").exists()
