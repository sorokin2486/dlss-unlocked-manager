"""User preferences (menu key, proxy DLL name, theme), stored as JSON next to the packages."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from . import package
from .installer import MENU_KEYS, PROXY_NAMES

LOG = logging.getLogger(__name__)
AUTO = "auto"
THEMES = ("system", "dark", "light")


@dataclass(frozen=True)
class Settings:
    menu_key: str = "F8"      # many compact keyboards have no Insert key
    proxy: str = AUTO         # AUTO = first free name among PROXY_NAMES
    theme: str = "system"

    def validated(self) -> Settings:
        """Replace any unknown value with its default, so a hand-edited file never breaks the app."""
        defaults = Settings()
        return Settings(
            menu_key=self.menu_key if self.menu_key in MENU_KEYS else defaults.menu_key,
            proxy=self.proxy if self.proxy == AUTO or self.proxy in PROXY_NAMES else defaults.proxy,
            theme=self.theme if self.theme in THEMES else defaults.theme,
        )


def settings_file() -> Path:
    return package.APP_DIR / "settings.json"


def load_settings() -> Settings:
    path = settings_file()
    if not path.is_file():
        return Settings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("expected an object")
    except (OSError, ValueError) as err:
        LOG.warning("Ignoring unreadable %s: %s", path, err)
        return Settings()
    known = {k: str(v) for k, v in raw.items() if k in Settings.__dataclass_fields__}
    return replace(Settings(), **known).validated()


def save_settings(settings: Settings) -> None:
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings.validated()), indent=2), encoding="utf-8")
