"""Install / uninstall the DLSS Unlocked standalone package into a game's exe folder.

Mirrors the official install.sh from github.com/ShyVortex/dlss-unlocked, including its
manifest (.dlss-unlocked.manifest) and backup suffix (.dlss-unlocked.bak), so installs made
by either tool can be upgraded or removed by the other.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

MANIFEST_NAME = ".dlss-unlocked.manifest"
BACKUP_SUFFIX = ".dlss-unlocked.bak"
CONFIG_NAME = "OptiScaler.ini"
PROXY_NAMES = ("dxgi", "version", "winmm", "dbghelp", "d3d12", "wininet", "winhttp")
REQUIRED_PAYLOAD = ("dxgi.dll", CONFIG_NAME, "OptiScaler")
_SKIP_FILES = frozenset({"install.sh", "how-to-install.txt"})
_SKIP_DIRS = frozenset({"repatch", "licenses"})


class InstallError(RuntimeError):
    """A user-facing installation failure."""


@dataclass(frozen=True)
class InstallResult:
    game_dir: Path
    proxy: str
    files: tuple[str, ...]
    backed_up: tuple[str, ...]
    kept_config: bool


def validate_package(package_dir: Path) -> None:
    missing = [n for n in REQUIRED_PAYLOAD if not (package_dir / n).exists()]
    if missing:
        raise InstallError(f"В папке мода нет: {', '.join(missing)} ({package_dir})")


def read_manifest(game_dir: Path) -> tuple[str, ...]:
    """Read installed relative paths, refusing any entry that would escape the game folder."""
    path = game_dir / MANIFEST_NAME
    if not path.is_file():
        return ()
    entries = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for entry in entries:
        pure = PurePosixPath(entry.replace("\\", "/"))
        if pure.is_absolute() or ".." in pure.parts or ":" in entry:
            raise InstallError(f"Подозрительная запись в манифесте: {entry!r}")
    return tuple(entries)


def choose_proxy(game_dir: Path) -> str:
    """First proxy DLL name that is free in the game folder (or already ours)."""
    ours = {e.lower() for e in read_manifest(game_dir)}
    for name in PROXY_NAMES:
        dll = f"{name}.dll"
        if dll in ours or not (game_dir / dll).exists():
            return name
    raise InstallError("Все имена прокси-DLL заняты другими модами")


def plan_payload(package_dir: Path, proxy: str, repatch: bool) -> list[tuple[Path, str]]:
    """(source file, destination path relative to the game folder) for every file to copy."""
    if proxy not in PROXY_NAMES:
        raise InstallError(f"Неизвестное имя прокси: {proxy}")
    plan: list[tuple[Path, str]] = []
    for src in sorted(p for p in package_dir.rglob("*") if p.is_file()):
        rel = src.relative_to(package_dir).as_posix()
        top = rel.split("/", 1)[0].lower()
        if rel.lower() in _SKIP_FILES:
            continue
        if rel == "REPatch/dinput8.dll":
            if repatch:
                plan.append((src, "dinput8.dll"))
            continue
        if top in _SKIP_DIRS:
            continue
        plan.append((src, f"{proxy}.dll" if rel == "dxgi.dll" else rel))
    return plan


def _prune_empty_dirs(game_dir: Path, entries: tuple[str, ...]) -> None:
    parents = {p for e in entries for p in PurePosixPath(e).parents if str(p) != "."}
    for rel in sorted(parents, key=lambda p: len(p.parts), reverse=True):
        try:
            (game_dir / rel).rmdir()
        except OSError:
            pass  # not empty or already gone


def _backup_path(game_dir: Path, rel: str) -> Path:
    return game_dir / f"{rel}{BACKUP_SUFFIX}"


def _write_manifest(game_dir: Path, entries: list[str]) -> None:
    path = game_dir / MANIFEST_NAME
    if entries:
        path.write_text("\n".join(entries) + "\n", encoding="utf-8")
    else:
        path.unlink(missing_ok=True)


def _remove_previous(game_dir: Path, *, keep_config: bool) -> list[str]:
    """Delete our files from the manifest and restore each original from its backup.

    Every entry is attempted; returns the entries that could not be removed (still ours),
    with the kept config listed first when it was skipped on purpose.
    """
    entries = read_manifest(game_dir)
    remaining: list[str] = []
    for rel in entries:
        if keep_config and rel == CONFIG_NAME:
            remaining.append(rel)
            continue
        target, backup = game_dir / rel, _backup_path(game_dir, rel)
        try:
            target.unlink(missing_ok=True)
            if backup.exists():
                backup.rename(target)
        except OSError:
            remaining.append(rel)
    _prune_empty_dirs(game_dir, entries)
    return remaining


def _locked_error(detail: str) -> InstallError:
    return InstallError(f"{detail}. Закройте игру и попробуйте снова.")


def _check_conflicts(game_dir: Path, plan: list[tuple[Path, str]], skip: set[str]) -> None:
    """Refuse to touch a file that exists next to a backup we did not account for."""
    conflicts = [rel for _, rel in plan if rel not in skip
                 and (game_dir / rel).exists() and _backup_path(game_dir, rel).exists()]
    if conflicts:
        raise InstallError(
            "Найдены и файл, и его резервная копия (*.dlss-unlocked.bak): "
            f"{', '.join(conflicts)}. Разберитесь с ними вручную, чтобы не потерять оригинал."
        )


def _copy_one(src: Path, game_dir: Path, rel: str) -> bool:
    """Copy one payload file, backing up a foreign original. Returns True if a backup was made.

    On failure the destination is rolled back to the original, so nothing foreign is lost.
    """
    dest, backup = game_dir / rel, _backup_path(game_dir, rel)
    backed_up = False
    if dest.exists():
        dest.rename(backup)
        backed_up = True
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    except OSError:
        dest.unlink(missing_ok=True)
        if backed_up:
            backup.rename(dest)
        raise
    return backed_up


def install(
    package_dir: Path,
    game_dir: Path,
    *,
    proxy: str | None = None,
    repatch: bool = False,
    reset_config: bool = False,
) -> InstallResult:
    validate_package(package_dir)
    if not game_dir.is_dir():
        raise InstallError(f"Папка игры не найдена: {game_dir}")
    keep_config = not reset_config and CONFIG_NAME in read_manifest(game_dir)
    proxy = proxy or choose_proxy(game_dir)
    plan = plan_payload(package_dir, proxy, repatch)
    if not plan:
        raise InstallError("В пакете мода нет файлов для установки")

    # Remove the previous install and restore originals (also covers a changed proxy name).
    remaining = _remove_previous(game_dir, keep_config=keep_config)
    stuck = [rel for rel in remaining if not (keep_config and rel == CONFIG_NAME)]
    if stuck:
        _write_manifest(game_dir, remaining)
        raise _locked_error(f"Не удалось удалить старые файлы мода: {', '.join(stuck)}")
    kept_config = keep_config and (game_dir / CONFIG_NAME).exists()
    _check_conflicts(game_dir, plan, {CONFIG_NAME} if kept_config else set())

    written: list[str] = [CONFIG_NAME] if kept_config else []
    backed_up: list[str] = []
    try:
        for src, rel in plan:
            if kept_config and rel == CONFIG_NAME:
                continue
            if _copy_one(src, game_dir, rel):
                backed_up.append(rel)
            written.append(rel)  # only after the copy succeeded: never list a foreign file
    except OSError as err:
        raise _locked_error(f"Не удалось записать файл ({err})") from err
    finally:
        _write_manifest(game_dir, written)  # partial installs stay removable

    return InstallResult(game_dir, proxy, tuple(written), tuple(backed_up), kept_config)


MENU_KEYS = {"Insert": 0x2D, "Home": 0x24, "Delete": 0x2E, "End": 0x23,
             **{f"F{n}": 0x6F + n for n in range(1, 13)}}  # F1 = 0x70 ... F12 = 0x7B
_SHORTCUT_LINE = re.compile(r"(?m)^ShortcutKey=[^\r\n]*")  # [^\r\n] keeps the line ending intact


def set_menu_key(game_dir: Path, key: str) -> None:
    """Set the OptiScaler overlay key (ShortcutKey in OptiScaler.ini), e.g. 'F8'."""
    if key not in MENU_KEYS:
        raise InstallError(f"Неизвестная клавиша: {key}. Можно: {', '.join(MENU_KEYS)}")
    ini = game_dir / CONFIG_NAME
    try:
        with ini.open(encoding="utf-8", newline="") as handle:  # keep CRLF line endings as is
            text = handle.read()
    except OSError as err:
        raise InstallError(f"Не удалось прочитать {ini}: {err}") from err
    if not _SHORTCUT_LINE.search(text):
        raise InstallError(f"В {CONFIG_NAME} нет строки ShortcutKey")
    updated = _SHORTCUT_LINE.sub(f"ShortcutKey=0x{MENU_KEYS[key]:02X}", text, count=1)
    with ini.open("w", encoding="utf-8", newline="") as handle:
        handle.write(updated)


def uninstall(game_dir: Path) -> tuple[str, ...]:
    entries = read_manifest(game_dir)
    if not entries:
        raise InstallError(f"Мод не установлен в {game_dir}")
    remaining = _remove_previous(game_dir, keep_config=False)
    _write_manifest(game_dir, remaining)
    if remaining:
        raise _locked_error(f"Не удалось удалить: {', '.join(remaining)}")
    return entries
