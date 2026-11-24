from pathlib import Path

from dlss_manager.installer import MANIFEST_NAME
from dlss_manager.scanner import Support, scan_game
from dlss_manager.steam import SteamGame


def _touch(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _game(root: Path) -> SteamGame:
    return SteamGame(app_id="42", name="Test Game", install_dir=root)


def test_unreal_layout_picks_shipping_exe_and_full_support(tmp_path):
    root = tmp_path / "UEGame"
    _touch(root / "UEGame.exe", b"tiny bootstrap")
    shipping = _touch(root / "UEGame" / "Binaries" / "Win64" / "UEGame-Win64-Shipping.exe", b"..D3D12.dll..")
    _touch(root / "UEGame" / "Binaries" / "Win64" / "CrashReportClient.exe", b"x" * 5000)
    plugin = root / "Engine" / "Plugins" / "Runtime" / "Nvidia" / "DLSS" / "Binaries" / "ThirdParty" / "Win64"
    _touch(plugin / "nvngx_dlss.dll")
    _touch(root / "UEGame" / "Binaries" / "Win64" / "sl.interposer.dll")
    _touch(root / "UEGame" / "Binaries" / "Win64" / "sl.dlss_g.dll")

    scan = scan_game(_game(root))

    assert scan.main_exe == shipping
    assert scan.exe_dir == shipping.parent
    assert (scan.has_dlss_sr, scan.has_dlss_fg, scan.has_streamline, scan.dx12_hint) == (True, True, True, True)
    assert scan.support is Support.FULL
    assert not scan.installed


def test_upscale_only_and_installed_flag(tmp_path):
    root = tmp_path / "Game"
    exe = _touch(root / "bin" / "x64" / "game.exe", b"vulkan only")
    _touch(root / "bin" / "x64" / "nvngx_dlss.dll")
    _touch(root / "bin" / "x64" / MANIFEST_NAME, b"dxgi.dll\n")

    scan = scan_game(_game(root))

    assert scan.main_exe == exe
    assert scan.support is Support.UPSCALE_ONLY
    assert scan.dx12_hint is False
    assert scan.installed is True


def test_anti_cheat_blocks_install(tmp_path):
    root = tmp_path / "Online"
    _touch(root / "game.exe")
    _touch(root / "nvngx_dlss.dll")
    _touch(root / "nvngx_dlssg.dll")
    _touch(root / "EasyAntiCheat" / "Settings.json")

    scan = scan_game(_game(root))

    assert scan.anti_cheat == ("EasyAntiCheat",)
    assert scan.support is Support.BLOCKED


def test_anti_cheat_installer_and_known_online_app_are_blocked(tmp_path):
    root = tmp_path / "Finals"
    _touch(root / "game.exe")
    _touch(root / "nvngx_dlss.dll")
    _touch(root / "nvngx_dlssg.dll")
    _touch(root / "Installers" / "AntiCheatInstaller.exe")
    assert scan_game(_game(root)).support is Support.BLOCKED

    clean = tmp_path / "Rivals"
    _touch(clean / "game.exe")
    _touch(clean / "nvngx_dlss.dll")
    _touch(clean / "nvngx_dlssg.dll")
    rivals = SteamGame(app_id="2767030", name="Marvel Rivals", install_dir=clean)
    assert scan_game(rivals).support is Support.BLOCKED


def test_exe_named_after_game_beats_bigger_tool(tmp_path):
    root = tmp_path / "Deadlock"
    real = _touch(root / "game" / "bin" / "win64" / "deadlock.exe", b"x" * 1000)
    _touch(root / "game" / "bin" / "win64" / "vconsole2.exe", b"x" * 5000)
    _touch(root / "game" / "bin" / "win64" / "mapper.exe", b"x" * 8000)

    game = SteamGame(app_id="1", name="Deadlock", install_dir=root)
    assert scan_game(game).main_exe == real


def test_re_engine_is_detected(tmp_path):
    root = tmp_path / "DD2"
    _touch(root / "DD2.exe")
    _touch(root / "re_chunk_000.pak")
    _touch(root / "nvngx_dlss.dll")
    _touch(root / "nvngx_dlssg.dll")

    scan = scan_game(_game(root))

    assert scan.re_engine is True
    assert scan.support is Support.FULL


def test_no_dlss_and_redist_is_ignored(tmp_path):
    root = tmp_path / "Old"
    exe = _touch(root / "old.exe")
    _touch(root / "_CommonRedist" / "nvngx_dlss.dll")  # redist folders are skipped
    _touch(root / "unins000.exe", b"x" * 10_000)

    scan = scan_game(_game(root))

    assert scan.main_exe == exe
    assert scan.support is Support.NONE
