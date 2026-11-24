from pathlib import Path

import pytest

from dlss_manager.steam import VdfError, installed_games, library_dirs, parse_vdf

LIBRARY_VDF = r'''
"libraryfolders"
{
    "0" { "path" "{steam}" "apps" { "10" "1" } }
    "1" { "path" "{lib}" }
    "2" { "path" "Z:\\missing" }
}
'''


def _acf(app_id: str, name: str, folder: str) -> str:
    return f'"AppState"\n{{\n "appid" "{app_id}"\n "name" "{name}"\n "installdir" "{folder}"\n}}\n'


def test_parse_vdf_handles_nesting_and_escapes():
    data = parse_vdf(r'"a" { "path" "C:\\Games\\X" "inner" { "q" "say \"hi\"" } }')
    assert data == {"a": {"path": r"C:\Games\X", "inner": {"q": 'say "hi"'}}}


@pytest.mark.parametrize("text", ['"a" { "b" "c"', '"a" "b" }', '{ "a" "b" }'])
def test_parse_vdf_rejects_unbalanced_input(text):
    with pytest.raises(VdfError):
        parse_vdf(text)


def _make_library(root: Path) -> Path:
    (root / "steamapps" / "common").mkdir(parents=True)
    return root


def test_library_dirs_reads_vdf_and_skips_missing(tmp_path):
    steam = _make_library(tmp_path / "steam")
    lib = _make_library(tmp_path / "lib")
    vdf = LIBRARY_VDF.replace("{steam}", str(steam).replace("\\", "\\\\")).replace(
        "{lib}", str(lib).replace("\\", "\\\\"))
    (steam / "steamapps" / "libraryfolders.vdf").write_text(vdf, encoding="utf-8")

    assert library_dirs(steam) == [steam, lib]


def test_installed_games_reads_manifests_and_filters_tools(tmp_path):
    lib = _make_library(tmp_path / "lib")
    apps = lib / "steamapps"
    (apps / "common" / "Game B").mkdir()
    (apps / "common" / "Game A").mkdir()
    (apps / "common" / "Proton 9.0").mkdir()
    (apps / "appmanifest_2.acf").write_text(_acf("2", "Beta Game", "Game B"), encoding="utf-8")
    (apps / "appmanifest_1.acf").write_text(_acf("1", "alpha game", "Game A"), encoding="utf-8")
    (apps / "appmanifest_3.acf").write_text(_acf("3", "Proton 9.0", "Proton 9.0"), encoding="utf-8")
    (apps / "appmanifest_4.acf").write_text(_acf("4", "Not Installed", "Gone"), encoding="utf-8")
    (apps / "appmanifest_5.acf").write_text("garbage {", encoding="utf-8")

    games = installed_games([lib])

    assert [(g.app_id, g.name) for g in games] == [("1", "alpha game"), ("2", "Beta Game")]
    assert games[0].install_dir == apps / "common" / "Game A"
