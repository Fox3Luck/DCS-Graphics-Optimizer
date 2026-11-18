# DCS Graphics Optimizer - Fox3 Managed Solutions Inc.
# Created 2026-11-17. Tests for the player's choice of map and aircraft for the test (issue #23).
import json
import zipfile

from dcstune import rate, scenes

from test_core import INFO


def test_pack_holds_every_offered_combination_as_a_loadable_mission(tmp_path):
    idx = scenes.index()
    assert len(idx["maps"]) == 12 and "Su-25T" in idx["aircraft"] and "F-14B" in idx["aircraft"]
    assert all(m["aircraft"] for m in idx["maps"].values())
    used = scenes.write_mission(("syria", "F-14B"), tmp_path / "a.miz")
    assert used == ("syria", "F-14B")
    with zipfile.ZipFile(tmp_path / "a.miz") as z:
        assert z.testzip() is None and sorted(z.namelist()) == sorted(idx["files"])
        mission = z.read("mission").decode()
    assert '["theatre"]="Syria"' in mission and '["type"]="F-14B"' in mission and '"Su-25T"' not in mission
    for unit in ("TUNE-CITY-1", "TUNE-RAMP-1", "TUNE-HIGH-1"):          # the names the camera follows
        assert f'"{unit}"' in mission
    with zipfile.ZipFile(tmp_path / "a.miz") as z:                          # a helicopter, on another map
        pass
    assert scenes.write_mission(("marianaislands", "AH-64D_BLK_II"), tmp_path / "b.miz") == ("marianaislands", "AH-64D_BLK_II")
    assert '"AH-64D_BLK_II"' in zipfile.ZipFile(tmp_path / "b.miz").read("mission").decode()


def test_anything_not_in_the_pack_falls_back_to_the_standard_test(tmp_path):
    for bad in (None, "syria", ("syria",), ("syria", "Spaceship"), ("atlantis", "F-14B"), ["syria", 14],
                ("normandy", "C-130J-30"),            # no ramp spot for it at that airfield, so not offered
                scenes.DEFAULT):
        assert scenes.valid(bad) is None
        assert scenes.write_mission(bad, tmp_path / "d.miz") == scenes.DEFAULT
        assert (tmp_path / "d.miz").read_bytes() == scenes.MISSION_SRC.read_bytes()
    assert scenes.label(None) == "Su-25T (free) over Caucasus (Batumi)"
    assert scenes.label(("syria", "F-14BU")) == "F-14B(U) over Syria (Beirut)"


def test_only_installed_maps_and_aircraft_are_offered(tmp_path):
    for folder in ("Mods/terrains/Syria", "Mods/terrains/MarianaIslands", "Mods/aircraft/F14", "Mods/aircraft/uh-1h"):
        (tmp_path / folder).mkdir(parents=True)
    have = scenes.installed(tmp_path)
    assert [m["key"] for m in have["maps"]] == ["caucasus", "syria", "marianaislands"]
    keys = [a["key"] for a in have["aircraft"]]
    assert "Su-25T" in keys and "F-14B" in keys and "F-14A-135-GR" in keys and "UH-1H" in keys      # folder case ignored
    assert "F-14BU" not in keys and "FA-18C_hornet" not in keys
    assert [m["key"] for m in scenes.installed(None)["maps"]] == ["caucasus"]                         # DCS not found
    # a map switched off in DCS's module manager cannot be loaded, so it is not offered (found on the test PC)
    profile = tmp_path / "profile"
    (profile / "Config").mkdir(parents=True)
    (profile / "Config" / "pluginsEnabled.lua").write_text(
        'pluginsEnabled = {\n    ["F-14B by Heatblur Simulations"] = false,\n    ["Syria"] = false,\n    ["MarianaIslands"] = true,\n}\n')
    have = scenes.installed(tmp_path, profile)
    assert [m["key"] for m in have["maps"]] == ["caucasus", "marianaislands"]
    assert "F-14B" in [a["key"] for a in have["aircraft"]]            # filmed from outside: still works
    assert scenes.switched_off(tmp_path / "nowhere") == set() and scenes.switched_off(None) == set()


def test_numbers_from_another_scene_are_kept_apart():
    flat = {"graphics.width": 2560, "graphics.height": 1440}
    plain = rate._fingerprint(INFO, flat)
    assert "scene" not in plain                                    # earlier saved calibrations stay valid
    picked = rate._fingerprint(dict(INFO, bench_scene=["syria", "F-14B"]), flat)
    assert picked["scene"] == ["syria", "F-14B"] and picked != plain
    assert rate._fingerprint(dict(INFO, bench_scene=["nowhere", "F-14B"]), flat) == plain


def test_busy_airfield_version_of_a_test(tmp_path):
    # Issues #23 and #35: every pair in the pack also has a version with the busy airfield scene.
    import re, zipfile
    idx = scenes.index()
    assert all(m["busy"] == m["aircraft"] for m in idx["maps"].values())
    assert scenes.busy_ok(None) and scenes.busy_ok(("syria", "F-14B")) and scenes.busy_ok(("nowhere", "F-14B"))   # bad pick = default pair
    assert scenes.write_mission(None, tmp_path / "d.miz", busy=True) == scenes.DEFAULT
    plain = zipfile.ZipFile(scenes.MISSION_SRC).read("mission").decode()
    for pick, name in ((None, "d.miz"), (("syria", "F-14B"), "s.miz")):
        scenes.write_mission(pick, tmp_path / name, busy=True)
        z = zipfile.ZipFile(tmp_path / name)
        text = z.read("mission").decode()
        for unit in ("TUNE-CITY-1", "TUNE-RAMP-1", "TUNE-HIGH-1", "TUNE-BUSY-1"):
            assert f'"{unit}"' in text
        assert len(re.findall(r'\["unitId"\]', text)) >= 170                     # 144 vehicles, 19 aircraft, the standard scenes
        assert "effectSmokeBig" in z.read("l10n/DEFAULT/dictionary").decode()
        assert '"UH-60A"' in text and '"M-1 Abrams"' in text
        # nothing can shoot: one side only, and no aircraft carries anything
        assert not re.search(r'\["pylons"\]\s*=\s*\{\s*\[', text)
    assert "TUNE-BUSY-1" not in plain                                              # the standard test is untouched
    scenes.write_mission(("syria", "F-14B"), tmp_path / "p.miz")
    assert "TUNE-BUSY-1" not in zipfile.ZipFile(tmp_path / "p.miz").read("mission").decode()


def test_busy_numbers_are_kept_apart():
    flat = {"graphics.width": 2560, "graphics.height": 1440}
    plain = rate._fingerprint(INFO, flat)
    busy = rate._fingerprint(dict(INFO, bench_busy=True), flat)
    assert busy.get("busy") is True and busy != plain
    assert rate._fingerprint(dict(INFO, bench_busy="yes"), flat) == plain          # only a real True counts
    both = rate._fingerprint(dict(INFO, bench_busy=True, bench_scene=["syria", "F-14B"]), flat)
    assert both["busy"] is True and both["scene"] == ["syria", "F-14B"]
