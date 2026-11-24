import zipfile
from pathlib import Path

import pytest

from dlss_manager import package
from dlss_manager.installer import InstallError


@pytest.fixture(autouse=True)
def isolated_app_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(package, "PACKAGES_DIR", tmp_path / "packages")
    monkeypatch.setattr(package, "DOWNLOADS_DIR", tmp_path / "downloads")


def _zip(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return path


PAYLOAD = {"dxgi.dll": "o", "OptiScaler.ini": "i", "OptiScaler/a.dll": "a"}


def test_extract_finds_payload_inside_top_folder(tmp_path):
    zip_path = _zip(tmp_path / "dlss-unlocked-standalone-v1.zip",
                    {f"dlss-unlocked/{k}": v for k, v in PAYLOAD.items()})

    root = package.resolve_package(zip_path)

    assert root.name == "dlss-unlocked"
    assert (root / "OptiScaler" / "a.dll").read_text() == "a"
    assert package.newest_local_package() == root
    assert package.extract_package(zip_path) == root  # second call reuses the extraction


def test_zip_slip_is_rejected(tmp_path):
    zip_path = _zip(tmp_path / "evil.zip", {**PAYLOAD, "../escape.dll": "x"})
    with pytest.raises(InstallError):
        package.extract_package(zip_path)
    assert not (tmp_path / "escape.dll").exists()


def test_non_mod_folder_and_bad_zip_are_rejected(tmp_path):
    (tmp_path / "random").mkdir()
    with pytest.raises(InstallError):
        package.resolve_package(tmp_path / "random")
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(InstallError):
        package.extract_package(bad)
