"""Finding DCS and its settings when they are not where the tool first looks
(beta feedback: DCS or Saved Games on another drive, Steam installs)."""
from pathlib import Path

import pytest

from dcstune import sysinfo, ui
from test_core import INFO


@pytest.fixture(autouse=True)
def appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


def make_install(root: Path, sub="bin") -> Path:
    (root / sub).mkdir(parents=True)
    (root / sub / "DCS.exe").write_bytes(b"MZ")
    (root / "autoupdate.cfg").write_text('{"version": "2.9.31.29434"}')
    return root


def make_profile(root: Path) -> Path:
    (root / "Config").mkdir(parents=True)
    (root / "Config" / "options.lua").write_text("options = {}\n")
    return root


def test_chosen_install_is_used_first_and_bin_folder_is_accepted(tmp_path):
    inst = make_install(tmp_path / "E" / "DCS World", "bin-mt")
    msg = sysinfo.choose("install", str(inst / "bin-mt"))
    assert str(inst) in msg
    info = sysinfo.apply_choices(dict(INFO, installs=[{"path": str(tmp_path), "media": "SSD"}]))
    first = sysinfo.pick_install(info)
    assert first["path"] == str(inst) and first["mt"] and first["version"] == "2.9.31.29434"
    assert len(info["installs"]) == 2


def test_folder_without_dcs_is_refused(tmp_path):
    with pytest.raises(RuntimeError, match="DCS.exe was not found"):
        sysinfo.choose("install", str(tmp_path))
    with pytest.raises(RuntimeError, match="No DCS settings"):
        sysinfo.choose("profile", str(tmp_path))
    assert not sysinfo.choices_file().exists()


@pytest.mark.parametrize("pick", ["saved_games", "profile", "config"])
def test_chosen_settings_folder_wins(tmp_path, pick):
    sg = tmp_path / "E" / "Saved Games"
    prof = make_profile(sg / "DCS")
    path = {"saved_games": sg, "profile": prof, "config": prof / "Config"}[pick]
    sysinfo.choose("profile", str(path))
    other = {"name": "DCS", "path": str(tmp_path / "C"), "options": "x", "modified": "2099-01-01T00:00:00"}
    info = sysinfo.apply_choices(dict(INFO, profiles=[other]))
    assert sysinfo.pick_profile(info)["path"] == str(prof)


def test_nothing_found_asks_the_player():
    with pytest.raises(sysinfo.SetupNeeded) as e:
        sysinfo.pick_profile(dict(INFO, profiles=[]))
    assert e.value.what == "profile" and "Browse" in str(e.value)
    with pytest.raises(sysinfo.SetupNeeded) as e:
        sysinfo.pick_install(dict(INFO, installs=[]))
    assert e.value.what == "install" and "registry" not in str(e.value).split("(")[0]


def test_window_shows_setup_instead_of_failing_silently(tmp_path):
    def no_profile():
        raise sysinfo.SetupNeeded("profile", "Your DCS settings folder was not found")
    app = ui.App(no_profile)
    sc = app.handle("GET", "/api/scorecard", {})
    assert sc["setup"]["what"] == "profile" and sc["can_browse"] is False
    # "Test and optimize" now says why it cannot start (it used to look like nothing happened).
    with pytest.raises(RuntimeError, match="settings folder was not found"):
        app.handle("POST", "/api/optimize", {"full": False})

    prof = make_profile(tmp_path / "Saved Games" / "DCS")
    built = []
    app._factory = lambda: built.append(1) or type("E", (), {"info": dict(INFO, installs=[])})()
    r = app.handle("POST", "/api/choose-folder", {"what": "profile", "path": str(prof)})
    assert str(prof) in r["message"]
    assert app.setup_needed()["what"] == "install"          # next it asks where DCS is
    assert built == [1]


def test_choose_folder_rejects_unknown_kind():
    with pytest.raises(KeyError):
        ui.App(lambda: None).handle("POST", "/api/choose-folder", {"what": "windows", "path": "C:\\"})
