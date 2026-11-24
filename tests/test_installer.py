from pathlib import Path

import pytest

from dlss_manager.installer import (
    BACKUP_SUFFIX,
    MANIFEST_NAME,
    InstallError,
    choose_proxy,
    install,
    read_manifest,
    uninstall,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def package(tmp_path) -> Path:
    root = tmp_path / "pkg"
    _write(root / "dxgi.dll", "optiscaler")
    _write(root / "OptiScaler.ini", "default ini")
    _write(root / "nvngx_dlssnr.dll", "nr")
    _write(root / "OptiScaler" / "dlssg_sm86" / "dlssg_sm86.dll", "sm86")
    _write(root / "REPatch" / "dinput8.dll", "reframework")
    _write(root / "REPatch" / "README.txt", "readme")
    _write(root / "Licenses" / "LICENSE.txt", "license")
    _write(root / "install.sh", "#!/bin/sh")
    _write(root / "HOW-TO-INSTALL.txt", "howto")
    return root


@pytest.fixture
def game(tmp_path) -> Path:
    root = tmp_path / "game" / "bin"
    _write(root / "game.exe", "exe")
    return root


def test_install_copies_payload_and_writes_manifest(package, game):
    result = install(package, game)

    assert result.proxy == "dxgi"
    assert set(read_manifest(game)) == {
        "dxgi.dll", "OptiScaler.ini", "nvngx_dlssnr.dll", "OptiScaler/dlssg_sm86/dlssg_sm86.dll"}
    assert (game / "OptiScaler" / "dlssg_sm86" / "dlssg_sm86.dll").read_text() == "sm86"
    assert not (game / "install.sh").exists()
    assert not (game / "Licenses").exists()
    assert not (game / "dinput8.dll").exists()


def test_install_backs_up_foreign_file_and_uninstall_restores(package, game):
    _write(game / "nvngx_dlssnr.dll", "original")

    result = install(package, game, proxy="dxgi")
    assert result.backed_up == ("nvngx_dlssnr.dll",)
    assert (game / f"nvngx_dlssnr.dll{BACKUP_SUFFIX}").read_text() == "original"

    uninstall(game)

    assert (game / "nvngx_dlssnr.dll").read_text() == "original"
    assert not (game / "dxgi.dll").exists()
    assert not (game / "OptiScaler").exists()
    assert not (game / MANIFEST_NAME).exists()
    assert (game / "game.exe").exists()


def test_auto_proxy_skips_names_taken_by_other_mods(package, game):
    _write(game / "dxgi.dll", "reshade")

    assert choose_proxy(game) == "version"
    result = install(package, game)

    assert result.proxy == "version"
    assert (game / "dxgi.dll").read_text() == "reshade"
    assert (game / "version.dll").read_text() == "optiscaler"


def test_reinstall_keeps_user_config_unless_reset(package, game):
    install(package, game)
    _write(game / "OptiScaler.ini", "my tweaks")

    assert install(package, game).kept_config is True
    assert (game / "OptiScaler.ini").read_text() == "my tweaks"
    assert choose_proxy(game) == "dxgi"  # our own dxgi.dll does not count as taken

    install(package, game, reset_config=True)
    assert (game / "OptiScaler.ini").read_text() == "default ini"


def test_reinstall_with_other_proxy_restores_original(package, game):
    _write(game / "version.dll", "game's own")
    install(package, game, proxy="version")
    assert (game / "version.dll").read_text() == "optiscaler"

    install(package, game, proxy="dxgi")

    assert (game / "version.dll").read_text() == "game's own"
    assert (game / "dxgi.dll").read_text() == "optiscaler"
    assert not (game / f"version.dll{BACKUP_SUFFIX}").exists()


def test_foreign_config_is_backed_up_not_kept(package, game):
    _write(game / MANIFEST_NAME, "dxgi.dll\n")  # old manifest that does not own the ini
    _write(game / "OptiScaler.ini", "someone else's")

    result = install(package, game)

    assert result.kept_config is False
    assert (game / f"OptiScaler.ini{BACKUP_SUFFIX}").read_text() == "someone else's"
    uninstall(game)
    assert (game / "OptiScaler.ini").read_text() == "someone else's"


def test_failed_copy_rolls_back_and_never_lists_foreign_file(package, game, monkeypatch):
    _write(game / "nvngx_dlssnr.dll", "original")
    real_copy = __import__("shutil").copy2

    def flaky_copy(src, dest):
        if Path(dest).name == "nvngx_dlssnr.dll":
            raise PermissionError("locked")
        return real_copy(src, dest)

    monkeypatch.setattr("dlss_manager.installer.shutil.copy2", flaky_copy)
    with pytest.raises(InstallError):
        install(package, game, proxy="dxgi")

    assert (game / "nvngx_dlssnr.dll").read_text() == "original"
    assert "nvngx_dlssnr.dll" not in read_manifest(game)
    monkeypatch.undo()
    uninstall(game)
    assert (game / "nvngx_dlssnr.dll").read_text() == "original"
    assert not (game / "dxgi.dll").exists()


def test_stale_backup_next_to_foreign_file_aborts(package, game):
    _write(game / "nvngx_dlssnr.dll", "new original")
    _write(game / f"nvngx_dlssnr.dll{BACKUP_SUFFIX}", "old backup")

    with pytest.raises(InstallError):
        install(package, game)

    assert (game / "nvngx_dlssnr.dll").read_text() == "new original"
    assert not (game / "dxgi.dll").exists()


def test_repatch_installs_reframework(package, game):
    install(package, game, repatch=True)
    assert (game / "dinput8.dll").read_text() == "reframework"


def test_manifest_with_path_traversal_is_rejected(game):
    _write(game / MANIFEST_NAME, "../../Windows/system32/evil.dll\n")
    with pytest.raises(InstallError):
        uninstall(game)


def test_invalid_package_and_missing_install(tmp_path, game):
    with pytest.raises(InstallError):
        install(tmp_path, game)
    with pytest.raises(InstallError):
        uninstall(game)
