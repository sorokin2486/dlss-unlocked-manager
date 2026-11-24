import pytest

from dlss_manager import library, package


@pytest.fixture(autouse=True)
def isolated_app_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(package, "APP_DIR", tmp_path / "app")
    monkeypatch.setattr(library, "find_steam_dir", lambda: tmp_path / "no-steam")


def test_custom_folders_persist_dedupe_and_remove(tmp_path):
    game = tmp_path / "Phantom.Blade.Zero-Release"
    game.mkdir()

    assert library.add_custom_folder(game) == [game]
    assert library.add_custom_folder(game) == [game]  # adding twice keeps one entry
    assert library.load_custom_folders() == [game]

    discovered = library.discover_games()
    assert [g.name for g in discovered] == ["Phantom Blade Zero-Release"]
    assert discovered[0].app_id.startswith(library.CUSTOM_ID_PREFIX)

    assert library.remove_custom_folder(game) == []
    assert library.discover_games() == []


def test_missing_folder_is_rejected_and_skipped(tmp_path):
    with pytest.raises(FileNotFoundError):
        library.add_custom_folder(tmp_path / "nope")

    gone = tmp_path / "gone"
    gone.mkdir()
    library.add_custom_folder(gone)
    gone.rmdir()
    assert library.discover_games() == []


def test_corrupt_list_is_set_aside(tmp_path):
    path = library.custom_folders_file()
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    assert library.load_custom_folders() == []
    assert path.with_suffix(".bad.json").exists()
