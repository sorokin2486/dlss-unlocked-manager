import json

import pytest

from dlss_manager import package
from dlss_manager.settings import AUTO, Settings, load_settings, save_settings, settings_file


@pytest.fixture(autouse=True)
def isolated_app_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(package, "APP_DIR", tmp_path / "app")


def test_defaults_when_missing():
    assert load_settings() == Settings(menu_key="F8", proxy=AUTO, theme="system")


def test_round_trip():
    save_settings(Settings(menu_key="Home", proxy="version", theme="dark"))
    assert load_settings() == Settings(menu_key="Home", proxy="version", theme="dark")


def test_bad_values_fall_back_to_defaults():
    path = settings_file()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"menu_key": "F99", "proxy": "evil", "theme": "dark", "extra": 1}), encoding="utf-8")
    assert load_settings() == Settings(theme="dark")

    path.write_text("[broken", encoding="utf-8")
    assert load_settings() == Settings()
