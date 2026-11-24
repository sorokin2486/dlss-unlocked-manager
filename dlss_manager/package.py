"""Get the DLSS Unlocked standalone package: GitHub release lookup, download, safe unzip."""
from __future__ import annotations

import json
import os
import re
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

from .installer import InstallError, REQUIRED_PAYLOAD

REPO = "ShyVortex/dlss-unlocked"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_PATTERN = re.compile(r"^dlss-unlocked-standalone-.+\.zip$", re.IGNORECASE)
USER_AGENT = "dlss-unlocked-manager"
CHUNK_BYTES = 1024 * 1024
HTTP_TIMEOUT_S = 60

APP_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DLSSUnlockedManager"
DOWNLOADS_DIR = APP_DIR / "downloads"
PACKAGES_DIR = APP_DIR / "packages"

ProgressFn = Callable[[int, int], None]


@dataclass(frozen=True)
class ReleaseAsset:
    tag: str
    name: str
    size: int
    url: str


def latest_release_asset() -> ReleaseAsset:
    request = urllib.request.Request(RELEASES_API, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
            release = json.load(response)
    except OSError as err:
        raise InstallError(f"Не удалось получить список релизов с GitHub: {err}") from err
    for asset in release.get("assets", []):
        if ASSET_PATTERN.match(asset.get("name", "")):
            return ReleaseAsset(
                tag=release.get("tag_name", "?"),
                name=asset["name"],
                size=int(asset["size"]),
                url=asset["browser_download_url"],
            )
    raise InstallError("В последнем релизе нет standalone .zip")


def download(asset: ReleaseAsset, progress: ProgressFn | None = None) -> Path:
    """Download the release zip (skipped if a complete copy already exists)."""
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    target = DOWNLOADS_DIR / asset.name
    if target.is_file() and target.stat().st_size == asset.size:
        return target
    partial = target.with_suffix(".part")
    request = urllib.request.Request(asset.url, headers={"User-Agent": USER_AGENT})
    received = 0
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response, partial.open("wb") as out:
            while chunk := response.read(CHUNK_BYTES):
                out.write(chunk)
                received += len(chunk)
                if progress:
                    progress(received, asset.size)
    except OSError as err:
        partial.unlink(missing_ok=True)
        raise InstallError(f"Ошибка загрузки: {err}") from err
    if received != asset.size:
        partial.unlink(missing_ok=True)
        raise InstallError(f"Файл скачан не полностью ({received} из {asset.size} байт)")
    partial.replace(target)
    return target


def find_payload_root(folder: Path) -> Path:
    """The zip may hold files at its root or inside one top folder; find where they are."""
    candidates = [folder, *(p for p in folder.iterdir() if p.is_dir())] if folder.is_dir() else []
    for candidate in candidates:
        if all((candidate / name).exists() for name in REQUIRED_PAYLOAD):
            return candidate
    raise InstallError(f"Это не пакет DLSS Unlocked: нет {', '.join(REQUIRED_PAYLOAD)} в {folder}")


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    for info in archive.infolist():
        pure = PurePosixPath(info.filename.replace("\\", "/"))
        if pure.is_absolute() or ".." in pure.parts or ":" in info.filename:
            raise InstallError(f"Небезопасный путь в архиве: {info.filename!r}")
    return archive.infolist()


def extract_package(zip_path: Path) -> Path:
    """Unzip into PACKAGES_DIR/<zip name> once and return the folder holding the payload."""
    destination = PACKAGES_DIR / zip_path.stem
    if destination.is_dir():
        try:
            return find_payload_root(destination)
        except InstallError:
            shutil.rmtree(destination)  # stale or broken extraction: redo it
    staging = destination.with_name(destination.name + ".tmp")
    shutil.rmtree(staging, ignore_errors=True)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(staging, members=_safe_members(archive))
    except (zipfile.BadZipFile, OSError) as err:
        shutil.rmtree(staging, ignore_errors=True)
        raise InstallError(f"Не удалось распаковать {zip_path.name}: {err}") from err
    staging.replace(destination)
    return find_payload_root(destination)


def resolve_package(path: Path) -> Path:
    """Accept either the downloaded .zip or an already extracted folder."""
    if path.is_file() and path.suffix.lower() == ".zip":
        return extract_package(path)
    if path.is_dir():
        return find_payload_root(path)
    raise InstallError(f"Не найден пакет мода: {path}")


def newest_local_package() -> Path | None:
    """Most recently extracted package, used when the user does not pick one."""
    if not PACKAGES_DIR.is_dir():
        return None
    folders = sorted(
        (p for p in PACKAGES_DIR.iterdir() if p.is_dir() and not p.name.endswith(".tmp")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for folder in folders:
        try:
            return find_payload_root(folder)
        except InstallError:
            continue
    return None
