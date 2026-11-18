# DCS Graphics Optimizer - Fox3 Managed Solutions Inc.
# Created 2026-11-11. Tests for VR headset detection, goals and advice.
import json
from pathlib import Path

from dcstune import model as M
from dcstune import optimize, rate, vr as V
from dcstune.optionslua import Options
from dcstune.sysinfo import normalize

from test_core import FIX, INFO, FakePC, _current

# What Pimax Play 1.42 leaves on a PC that used a Crystal Light (read from the test box).
PIMAX_PROFILE = json.dumps({"": None, "Pimax P3C9": None, "enable_foveated_rendering": 1,
                            "pixels_per_display_pixel_rate": 0.8249216675758362, "ipd": 0.058})
RAW_VR = {"runtime": r"C:\Program Files\Pimax\Runtime\PiOpenXR_64.json", "layers": [], "pimax_profile": PIMAX_PROFILE}
VR_INFO = dict(INFO, vr=RAW_VR)
QUIET = lambda *_: None


def _vr(**over):
    return _current() | {"VR.enable": True} | over


def test_detects_pimax_headset_and_render_quality():
    d = V.detect(RAW_VR)
    assert d["runtime"] == "Pimax" and d["headset"] == "Pimax Crystal Light"
    assert d["render_quality"] == 0.82 and d["vendor_foveation"] and not d["quad_layer"]
    assert V.detect({"runtime": r"C:\Program Files (x86)\Steam\steamapps\common\SteamVR\steamxr_win64.json",
                     "layers": ["C:\\x\\quad-views-foveated.json"]}) | {"layers": 0} == {
        "runtime": "SteamVR", "headset": None, "render_quality": None, "layers": 0, "quad_layer": True,
        "detected": False}
    assert V.detect(None)["runtime"] is None and V.detect({"pimax_profile": "not json"})["headset"] is None
    # a single API layer arrives from PowerShell as a string, not a list
    assert normalize({"vr": {"layers": "one.json"}})["vr"]["layers"] == ["one.json"]


def test_state_is_none_on_a_monitor_and_describes_the_headset_in_vr():
    assert V.state(VR_INFO, _current() | {"VR.enable": False}) is None
    st = V.state(VR_INFO, _vr())
    assert st["known"] and st["hires"] and st["refresh"] == [72, 90, 120] and st["target"] == 90
    assert st["steps"] == [90, 72, 36] and not st["eye_tracking"]
    unknown = V.state(dict(INFO, vr={"runtime": "x\\oculus\\oculus_openxr_64.json"}), _vr())
    assert not unknown["known"] and not unknown["hires"] and unknown["runtime"] == "Meta (Oculus)"
    assert V.state(INFO, _vr())["runtime"] is None           # nothing detected: still works


def test_vr_scorecard_uses_the_headset_goal_and_says_it_is_rough():
    machine = rate.rate_machine(VR_INFO)
    flat_fit = rate.rate_settings(VR_INFO, _current() | {"VR.enable": False}, machine)
    fit = rate.rate_settings(VR_INFO, _vr(), machine)
    assert fit["vr"] and not flat_fit["vr"]
    assert fit["target_fps"] == 90 and flat_fit["target_fps"] == 120
    assert fit["basis"] == "rough estimate for VR, not measured"
    assert fit["fps"] < flat_fit["fps"]                      # a headset is far more pixels than 1440p
    assert not any("desktop is" in f["text"] for f in fit["findings"])
    rows = {r["label"]: r["value"] for r in rate.hardware_summary(VR_INFO, _vr())}
    assert rows["VR headset"] == "Pimax Crystal Light (2880 x 2880 per eye)"
    assert rows["VR software"] == "Pimax, render quality 0.82"
    assert "VR headset" not in {r["label"] for r in rate.hardware_summary(VR_INFO, _current())}


def test_vr_model_follows_density_render_quality_and_quad_views():
    st = V.state(VR_INFO, _vr())
    mdl = M.Model(78, 100, 2560, 1440, vr=st["model"])
    cur, rung = _vr(), M.current_rung(_vr(), "nvidia")
    base = mdl.frame_ms(cur, rung)
    assert mdl.frame_ms(cur | {"VR.pixel_density": 1.5}, rung) > base
    assert mdl.frame_ms(cur | {"VR.openxr_quadView": True}, rung) <= base
    assert mdl.vram_mb(cur | {"VR.pixel_density": 1.5}, rung) > mdl.vram_mb(cur, rung)
    slow = M.Model(40, 100, 2560, 1440, vr=dict(st["model"], render_quality=1.0))
    assert slow.frame_ms(cur, rung) > M.Model(40, 100, 2560, 1440, vr=st["model"]).frame_ms(cur, rung)


def test_vr_findings():
    machine = rate.rate_machine(VR_INFO)
    def texts(**over):
        return " | ".join(f["text"] for f in rate.rate_settings(VR_INFO, _vr(**over), machine)["findings"])
    assert "pixel density is 1.40" in texts(**{"VR.pixel_density": 1.4})
    assert "pixel density" not in texts(**{"VR.pixel_density": 1.0})
    quad = texts(**{"VR.openxr_quadView": True, "VR.bloom": True, "graphics.LensEffects": 3})
    assert "Bloom is on together with quad views" in quad and "Lens effects are on together" in quad
    assert "Motion blur" in texts(**{"graphics.motionBlur": 1})
    assert "can also run at 72, 120 Hz (Pimax Play)" in texts()
    # things that live in the headset software are marked as not changed by this tool
    fit = rate.rate_settings(VR_INFO, _vr(), machine)
    assert all(f.get("untouched") for f in fit["findings"] if "Pimax Play" in f["text"])


def test_fixed_vr_changes_only_touch_what_differs():
    st = V.state(VR_INFO, _vr(**{"VR.pixel_density": 1.3}))
    opts = _vr(**{"VR.pixel_density": 1.3, "VR.bloom": True, "graphics.motionBlur": 1, "graphics.DOF": 0,
                  "graphics.LensEffects": 3})
    assert V.fixed_changes(st, opts) == {"VR.pixel_density": 1.0, "graphics.motionBlur": 0}   # quad views off: bloom stays
    st_q = V.state(VR_INFO, opts | {"VR.openxr_quadView": True})
    assert V.fixed_changes(st_q, opts) == {"VR.pixel_density": 1.0, "graphics.motionBlur": 0,
                                           "VR.bloom": False, "graphics.LensEffects": 0}
    low = _vr(**{"VR.pixel_density": 0.8, "graphics.motionBlur": 0})
    assert "VR.pixel_density" not in V.fixed_changes(V.state(VR_INFO, low), low)   # the player's own trade
    unknown = V.state(INFO, opts)
    assert "VR.pixel_density" not in V.fixed_changes(unknown, opts)                # unknown headset: leave it
    assert "VR.openxr_quadView" not in json.dumps(V.FIXED)                         # never switched by the tool


def test_vr_run_carries_fixed_changes_and_headset_goals():
    cur = _vr(**{"VR.pixel_density": 1.3, "graphics.motionBlur": 1})
    st = V.state(VR_INFO, cur)
    extra = V.fixed_changes(st, cur)
    truth = M.Model(60, 100, 2560, 1440, vr=st["model"])
    pc = FakePC(cur, 60, 100)
    pc.truth = truth
    mdl = M.Model(78, 100, 2560, 1440, vr=dict(st["model"], pd=1.0))
    out = optimize.run(mdl, cur, "nvidia", st["target"], 16376, pc.measure, log=QUIET, steps=st["steps"], extra=extra)
    assert out["target_fps"] in st["steps"] and out["display_target"] == 90
    assert out["history"] and all(h["changes"]["VR.pixel_density"] == 1.0 and h["changes"]["graphics.motionBlur"] == 0
                                  for h in out["history"])
    rows = {r["key"]: r for r in optimize.describe_changes(cur, out["history"][0]["changes"], "nvidia", mdl,
                                                           1000 / out["before"]["avg_fps"])}
    assert rows["VR.pixel_density"]["from"] == "1.30" and rows["VR.pixel_density"]["to"] == "1.00"
    assert rows["VR.pixel_density"]["cost_pct"] < 0 and rows["graphics.motionBlur"]["to"] == "Off"
    assert rows["graphics.motionBlur"]["label"] == "Motion blur" and rows["graphics.motionBlur"]["why"]


def test_monitor_and_headset_results_are_kept_apart(tmp_path):
    flat, vr = _current() | {"VR.enable": False}, _vr()
    assert rate.config_key(flat) != rate.config_key(vr)
    assert rate.config_key(vr) != rate.config_key(vr | {"VR.pixel_density": 1.2})
    assert rate.config_key(flat) == rate.config_key(flat | {"VR.pixel_density": 1.2})   # irrelevant on a monitor
    profile = {"path": str(tmp_path)}
    (tmp_path / "Config").mkdir()
    learned = {"calibration": 1.1, "vram_offset": 0.0, "low_ratio": 0.7, "measured": {}}
    rate.save_calibration(profile, VR_INFO, flat, learned)
    assert rate.load_calibration(profile, VR_INFO, flat) and rate.load_calibration(profile, VR_INFO, vr) is None


def test_vr_keys_are_written_without_disturbing_the_file():
    path = FIX / "options.DCS.lua"
    o = Options.load(path)
    before = path.read_bytes().decode("utf-8", errors="surrogateescape").splitlines()
    o.update({"VR.pixel_density": 1.2, "VR.bloom": False})
    after = o.dumps().decode("utf-8", errors="surrogateescape").splitlines()
    changed = [(a, b) for a, b in zip(before, after) if a != b]
    assert len(before) == len(after) and len(changed) == 2
    again = Options(o.dumps().decode("utf-8", errors="surrogateescape"))
    assert again.section("VR")["pixel_density"] == 1.2 and again.section("VR")["bloom"] is False


# -- through the app's own engine ---------------------------------------------
class _FakeBench:
    """Stands in for bench.Bench: a FakePC behind the same interface."""
    made = []
    other_vram_mb = 0.0             # video memory other programs hold before DCS starts

    def __init__(self, profile, exe, log=print, vr=False, vram_total_mb=0, scene=None):
        self.vr, self.runs, self.keep_shots, self.scene = vr, 0, set(), scene
        self.options = profile["options"]
        _FakeBench.made.append(self)

    def __enter__(self):
        flat = rate.flat_options(Options.load(self.options)) | {"graphics.width": 2560, "graphics.height": 1440}
        self.pc = FakePC(flat, 50, 95)
        if self.vr:
            self.pc.truth = M.Model(50, 95, 2560, 1440, vr=V.state(VR_INFO, flat)["model"])
        return self

    def __exit__(self, *exc):
        return False

    def measure(self, changes):
        self.runs += 1
        return self.pc.measure(changes)

    measure_fast = measure
    measure_batch = None


def _engine(tmp_path, monkeypatch, **vr_options):
    import shutil
    from dcstune import bench, sysinfo, ui
    cfg = tmp_path / "Config"
    cfg.mkdir()
    shutil.copy(FIX / "options.DCS.lua", cfg / "options.lua")
    o = Options.load(cfg / "options.lua")
    o.update({"VR.enable": True, "graphics.width": 2560, "graphics.height": 1440} | vr_options)
    o.save(cfg / "options.lua")
    monkeypatch.setattr(bench, "Bench", _FakeBench)
    monkeypatch.setattr(bench, "dcs_running", lambda: False)
    monkeypatch.setattr(sysinfo, "pick_install", lambda info: {})
    monkeypatch.setattr(sysinfo, "dcs_exe", lambda inst: Path("DCS.exe"))
    eng = ui.Engine.__new__(ui.Engine)
    eng.info = dict(VR_INFO, profiles=[{"name": "DCS"}])
    eng.profile = {"name": "DCS", "path": str(tmp_path), "options": str(cfg / "options.lua")}
    eng.recovered = False
    return eng


def test_with_vr_on_the_released_test_stays_on_the_monitor(tmp_path, monkeypatch):
    monkeypatch.delenv("DCSTUNE_VR_BENCH", raising=False)
    eng = _engine(tmp_path, monkeypatch, **{"VR.pixel_density": 1.3})
    sc = eng.scorecard()
    assert sc["vr"] and not sc["vr_tested"] and sc["settings"]["vr"]
    assert any(r["label"] == "VR headset" for r in sc["hardware"])
    log = []
    rep = eng.optimize(False, log.append)
    assert not _FakeBench.made[-1].vr and rep["vr_skipped"] and not rep["vr"]
    assert any("runs on the monitor" in line for line in log)
    assert not rep["before"]["vr"] and rep["before"]["basis"] == "measured"
    assert not any(k.startswith("VR.") for k in rep.get("changes", {}))
    from dcstune import report as R
    assert "This test ran on the monitor" in R.fragment(rep)
    assert "vram_other_mb" not in rep and "Other programs were using" not in R.fragment(rep)


def test_video_memory_held_by_other_programs_is_noted_on_the_report(tmp_path, monkeypatch):
    eng = _engine(tmp_path, monkeypatch)
    monkeypatch.setattr(_FakeBench, "other_vram_mb", 7200.0)
    rep = eng.optimize(False, lambda m: None)
    from dcstune import report as R
    assert rep["vram_other_mb"] == 7200
    assert "Other programs were using 7.0 GB of video memory" in R.fragment(rep)


def test_experimental_vr_test_measures_in_the_headset_and_recommends_vr_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("DCSTUNE_VR_BENCH", "1")
    eng = _engine(tmp_path, monkeypatch, **{"VR.pixel_density": 1.3})
    assert eng.scorecard()["vr_tested"]
    rep = eng.optimize(False, lambda *_: None)
    assert _FakeBench.made[-1].vr and rep["vr"] and not rep["vr_skipped"]
    assert rep["before"]["vr"] and rep["target_fps"] in (90, 72, 36)
    assert rep["changes"]["VR.pixel_density"] == 1.0
    assert any(c["label"] == "VR pixel density" for c in rep["change_list"])
    eng.apply()
    assert Options.load(eng.profile["options"]).section("VR")["pixel_density"] == 1.0
    eng.undo()
    assert Options.load(eng.profile["options"]).section("VR")["pixel_density"] == 1.3


def test_report_folder_gets_an_audit_file_without_personal_details(tmp_path, monkeypatch):
    monkeypatch.delenv("DCSTUNE_VR_BENCH", raising=False)
    from dcstune import __version__, sysinfo
    eng = _engine(tmp_path, monkeypatch, **{"VR.pixel_density": 1.3})
    eng.info = dict(eng.info, vr=dict(RAW_VR, layers=[r"C:\Users\Maverick\AppData\Local\layers\quad-views-foveated.json"]))
    monkeypatch.setattr(sysinfo, "pick_install", lambda info: {
        "version": "2.9.31.29434", "variant": "", "mt": True, "media": "SSD", "path": r"C:\Users\Maverick\DCS World"})
    rep = eng.optimize(False, lambda *_: None)
    f = tmp_path / "DCS Graphics Optimizer Reports" / rep["dir"] / "audit.json"
    text = f.read_text()
    a = json.loads(text)
    assert a["schema"] == "dcsgo-audit/1" and a["tool_version"] == __version__
    assert a["hardware"]["cpu"] == INFO["cpu"] and a["hardware"]["gpu"]["name"] == INFO["gpu"]["name"]
    assert a["dcs"] == {"version": "2.9.31.29434", "variant": "", "mt": True, "media": "SSD"}
    v = a["vr"]
    assert v["enabled"] and v["runtime_file"] == "PiOpenXR_64" and v["detected"]["headset"] == "Pimax Crystal Light"
    assert v["detected"]["layers"] == ["quad-views-foveated"] and v["pimax"]["models"] == ["P3C9"]
    assert v["pimax"]["values"]["enable_foveated_rendering"] == 1 and v["rated_as"]["target"] == 90
    assert v["options"]["pixel_density"] == 1.3 and v["options"]["enable"] is True      # the player's real settings
    assert a["graphics"]["width"] == 2560 and a["test"]["vr_skipped"] is True
    assert a["test"]["before_result"]["avg_fps"] > 0 and a["settings_rating_before"]["grade"]
    # no names, folders or body measurements
    low = text.lower()
    assert "maverick" not in low and "users" not in low and ":\\\\" not in text and "ipd" not in low
    assert str(tmp_path).lower() not in low


def test_audit_survives_missing_information():
    from dcstune import audit
    a = audit.build({"cpu": "x"}, {}, {})
    assert a["vr"]["enabled"] is False and a["vr"]["pimax"] is None and a["graphics"] == {} and a["test"] == {}


def test_pimax_without_a_model_is_named_by_brand():
    from dcstune import vr
    base = {"headset": None, "known": False, "eye_w": 1, "eye_h": 1}
    assert vr.describe(dict(base, runtime="Pimax")) == "Pimax headset (model not known yet)"
    assert vr.describe(dict(base, runtime="SteamVR")) == "Headset not recognized"


def test_monitor_result_is_not_applied_to_a_vr_profile_without_asking(tmp_path, monkeypatch):
    # Beta feedback: VR players applied a monitor-tested result and their headset frame rate
    # halved ("from 60-70 to 18-25"). DCS uses the same graphics settings in the headset.
    import pytest
    eng = _engine(tmp_path, monkeypatch)
    rep = eng.optimize(False, lambda *_: None)
    assert rep["vr_skipped"]
    if not rep.get("changes"):
        pytest.skip("nothing recommended in this fixture")
    before = Path(eng.profile["options"]).read_bytes()
    with pytest.raises(RuntimeError, match=r"^\[vr\] "):
        eng.apply()
    assert Path(eng.profile["options"]).read_bytes() == before
    assert "Applied" in eng.apply(vr_ok=True)


VD_RAW = {"runtime": r"C:\Program Files\Virtual Desktop Streamer\OpenXR\virtualdesktop-openxr.json", "layers": []}


def test_player_picks_a_headset_the_tool_cannot_read():
    # Virtual Desktop and Link do not say which headset is connected: the player's pick is used
    st = V.state(dict(INFO, vr=dict(VD_RAW, chosen="Meta Quest 3")), _vr())
    assert st["runtime"] == "Virtual Desktop" and st["headset"] == "Meta Quest 3" and st["known"]
    assert not st["detected"] and (st["eye_w"], st["eye_h"]) == (2064, 2208)
    assert st["target"] == 90 and st["steps"] == [90, 80, 72, 36] and not st["hires"]
    pico = V.state(dict(INFO, vr=dict(VD_RAW, chosen="Pico 4 Ultra")), _vr())
    assert pico["refresh"] == [72, 90] and pico["steps"] == [90, 72, 36]
    # an unknown name is ignored, and what Pimax Play reports wins over a pick
    assert not V.state(dict(INFO, vr=dict(VD_RAW, chosen="Made Up 9000")), _vr())["known"]
    assert V.state(dict(INFO, vr=dict(RAW_VR, chosen="Meta Quest 3")), _vr())["headset"] == "Pimax Crystal Light"
    assert all(h in V.headset_names() for h in ("Meta Quest 3", "Pico 4 Ultra", "Valve Index", "HP Reverb G2"))
    for h in V.TABLE["headsets"]:
        assert h["eye_w"] > 0 and h["eye_h"] > 0 and h["refresh"] == sorted(h["refresh"])


def test_headset_pick_is_kept_and_shown_in_the_window(tmp_path, monkeypatch):
    from dcstune import prefs as F
    eng = _engine(tmp_path, monkeypatch)
    eng.info["vr"] = dict(VD_RAW)
    F.set_pref(eng.profile, "share", True)        # an answer left by an older version
    sc = eng.scorecard()
    assert sc["headset"]["name"] is None and not sc["headset"]["detected"] and "Meta Quest 3" in sc["headset"]["choices"]
    assert "Meta Quest 3" in eng.set_headset("Meta Quest 3")
    sc = eng.scorecard()
    assert sc["headset"]["name"] == "Meta Quest 3"
    assert any(r["value"].startswith("Meta Quest 3 (2064 x 2208") for r in sc["hardware"])
    # kept next to other saved answers, neither one overwriting the other
    assert F.get_pref(eng.profile, "headset") == "Meta Quest 3" and F.get_pref(eng.profile, "share") is True
    assert "cleared" in eng.set_headset("<script>")
    assert F.get_pref(eng.profile, "headset") is None and eng.scorecard()["headset"]["name"] is None
    # a Pimax headset is read from Pimax Play, so no picker
    eng.info["vr"] = dict(RAW_VR)
    assert eng.scorecard()["headset"]["detected"]


def test_vr_test_build_switches_on_testing_in_the_headset(tmp_path, monkeypatch):
    monkeypatch.delenv("DCSTUNE_VR_BENCH", raising=False)
    assert not V.test_build() and not V.bench_enabled()        # the public build never has the marker
    marker = tmp_path / "vr_test_build"
    marker.write_text("x")
    monkeypatch.setattr(V, "TEST_BUILD_MARKER", marker)
    assert V.test_build() and V.bench_enabled()
    eng = _engine(tmp_path, monkeypatch)
    sc = eng.scorecard()
    assert sc["vr_test_build"] and sc["vr_tested"]
    rep = eng.optimize(False, lambda m: None)
    assert _FakeBench.made[-1].vr and rep["vr"] and not rep["vr_skipped"]


def test_vr_goal_never_trades_frame_rate_for_picture(monkeypatch):
    """VR beta feedback (#30): a 90 Hz headset holding 72 was given settings for 45 (half rate)
    and dropped to 58 FPS. In VR the half rate is a last resort, never a way to gain picture."""
    top = M.max_quality("nvidia")
    # quality the search could reach at each goal; 90 and 72 only with a heavily cut picture
    reach = {90: (0.3, True), 80: (0.35, True), 72: (0.45, True), 45: (0.9, True), 36: (0.95, True)}
    monkeypatch.setattr(optimize, "choose", lambda mdl, t, *a: ({"q": reach[t][0]}, 0, reach[t][1]))

    class Mdl:
        vendor = "nvidia"
        def quality(self, cfg, rung):
            return cfg["q"] * top
    pick = lambda steps, low, **k: optimize.pick_target(Mdl(), 90, 16376, 0.8, steps, current_low=low, **k)
    assert pick(V.goal_steps([90], 90), 72) == 90                 # Varjo Aero: stay at the headset's rate
    assert pick(V.goal_steps([72, 80, 90, 120], 90), 85) == 80    # holds 80 already: never aim lower
    assert pick(V.goal_steps([72, 80, 90, 120], 90), 50) == 72    # lowest real refresh rate, not 36
    reach[90] = (0.6, True)
    assert pick(V.goal_steps([90], 90), 72) == 90                 # good enough picture at full rate
    reach.update({90: (0.1, False), 80: (0.1, False), 72: (0.1, False)})
    assert pick(V.goal_steps([72, 80, 90, 120], 90), 30) == 36    # nothing holds a real rate: half rate
    # on a monitor nothing changes
    reach[60] = (0.9, True)
    assert optimize.pick_target(Mdl(), 90, 16376, 0.8) == 60


QUEST3 = dict(INFO, vr={"runtime": r"C:\Program Files\Virtual Desktop Streamer\OpenXR\virtualdesktop-openxr.json",
                        "layers": [], "chosen": "Meta Quest 3"})


def test_headset_refresh_rate_the_player_picked_becomes_the_goal():
    # Issue #40: a Quest 3 flown at 72 Hz was tested against 90.
    st = V.state(QUEST3, _vr())
    assert st["target"] == 90 and not st["hz_chosen"] and st["steps"] == [90, 80, 72, 36]
    st = V.state(dict(QUEST3, vr=dict(QUEST3["vr"], hz=72)), _vr())
    assert st["target"] == 72 and st["hz_chosen"] and st["steps"] == [72, 36]
    st = V.state(dict(QUEST3, vr=dict(QUEST3["vr"], hz=120)), _vr())
    assert st["target"] == 120 and st["steps"] == [120, 90, 80, 72, 36]
    for bad in (75, "72", True, None, 0):          # only a rate this headset really has counts
        st = V.state(dict(QUEST3, vr=dict(QUEST3["vr"], hz=bad)), _vr())
        assert st["target"] == 90 and not st["hz_chosen"]
    machine = rate.rate_machine(QUEST3)
    said = lambda info: " ".join(f["text"] for f in rate.rate_settings(info, _vr(), machine)["findings"])
    assert "pick it under the profile name" in said(QUEST3)
    assert "the 72 Hz you picked" in said(dict(QUEST3, vr=dict(QUEST3["vr"], hz=72)))


def test_window_keeps_the_picked_refresh_rate_and_tests_for_it(tmp_path, monkeypatch):
    monkeypatch.setenv("DCSTUNE_VR_BENCH", "1")
    eng = _engine(tmp_path, monkeypatch)
    eng.info = dict(QUEST3, profiles=[{"name": "DCS"}])
    eng.set_headset("Meta Quest 3")
    h = eng.scorecard()["headset"]
    assert h["refresh"] == [72, 80, 90, 120] and h["hz"] == 90 and not h["hz_chosen"]
    assert "72 Hz" in eng.set_headset_hz(72)
    h = eng.scorecard()["headset"]
    assert h["hz"] == 72 and h["hz_chosen"]
    assert json.loads((tmp_path / "Config" / "dcstune-prefs.json").read_text())["headset_hz"] == 72
    log = []
    rep = eng.optimize(False, log.append)
    assert rep["vr"] and rep["target_fps"] in (72, 36) and rep["goal_chosen"] == 72
    assert any("Your own goal: 72 FPS" in line for line in log)
    assert "automatic" in eng.set_headset_hz(75)                 # not a Quest 3 rate: back to the usual one
    assert eng.scorecard()["headset"]["hz"] == 90


def test_own_frame_rate_goal_for_monitor_tests(tmp_path, monkeypatch):
    # Issue #45: "my monitors are 60 Hz but I'm perfectly fine running DCS at 30 fps".
    from dcstune import report as R
    assert rate.chosen_goal({"fps_goal": 30}) == 30 and rate.display_goal(dict(INFO, fps_goal=45)) == 45
    for bad in (31, "30", True, None, 0, 500):
        assert rate.chosen_goal({"fps_goal": bad}) is None
    assert rate.display_goal(INFO) == rate.target_fps(INFO["gpu"].get("refresh"))
    monkeypatch.delenv("DCSTUNE_VR_BENCH", raising=False)
    eng = _engine(tmp_path, monkeypatch)
    o = Options.load(eng.profile["options"])
    o.update({"VR.enable": False})
    o.save(eng.profile["options"])
    eng.info = dict(INFO, profiles=[{"name": "DCS"}])
    sc = eng.scorecard()
    assert sc["goal"]["chosen"] is None and 30 in sc["goal"]["choices"] and sc["headset"] is None
    auto = eng.optimize(False, lambda m: None)
    assert auto["goal_chosen"] is None and auto["target_fps"] >= 60 and "your own goal" not in R.fragment(auto)
    assert "30 FPS" in eng.set_goal(30)
    assert eng.scorecard()["goal"]["chosen"] == 30
    assert eng.scorecard()["settings"]["target_fps"] == 30       # the scorecard is graded against it too
    log = []
    rep = eng.optimize(False, log.append)
    assert rep["target_fps"] == 30 and rep["goal_chosen"] == 30 and rep["target_reached"]
    assert any("Your own goal: 30 FPS." in line for line in log)
    assert "from your own goal of 30 FPS" in R.fragment(rep)
    # a lower goal leaves room for a better-looking picture than the automatic one found
    quality = lambda r: r["after"]["quality_share"] if "after" in r else r["before"]["quality_share"]
    assert quality(rep) >= quality(auto)
    assert "automatic" in eng.set_goal(33)                       # not one of the choices: back to automatic
    assert eng.scorecard()["goal"]["chosen"] is None


def test_dream_air_and_unlisted_headsets_can_pick_their_rate():
    """A Dream Air owner runs 72 Hz; it was not in the list, and an unlisted headset could only get 90."""
    from dcstune import vr as V
    opts = {"VR.enable": True}
    dream = V.state({"vr": {"runtime": "Pimax", "chosen": "Pimax Dream Air", "hz": 72}}, opts)
    assert dream["known"] and dream["target"] == 72 and dream["steps"] == [72, 36] and dream["refresh"] == [72, 90]
    unknown = V.state({"vr": {"runtime": "VirtualDesktop", "hz": 72}}, opts)
    assert unknown["known"] is False and unknown["hz_chosen"] and unknown["target"] == 72
    assert unknown["refresh"] == [72, 80, 90, 120] and unknown["steps"] == [72, 36]
    auto = V.state({"vr": {"runtime": "VirtualDesktop"}}, opts)
    assert auto["target"] == 90 and auto["steps"] == [90, 45] and not auto["hz_chosen"]
    assert any(h["name"] == "Pimax Dream Air" and h["refresh"] == [72, 90] for h in V.TABLE["headsets"])


def test_own_headset_goal_half_rate_for_motion_smoothing():
    # Issue #47: a VR tester flies with motion smoothing and wants 36 at 72 Hz, 45 at 90 Hz, or 50 for headroom.
    assert [V.own_goal(hz, "half") for hz in (72, 80, 90, 120)] == [36, 40, 45, 60]
    assert [V.own_goal(hz, "half_room") for hz in (72, 80, 90, 120)] == [40, 44, 50, 66]
    st = V.state(dict(QUEST3, vr=dict(QUEST3["vr"], goal="half")), _vr())
    assert st["hz"] == 90 and st["target"] == 45 and st["goal_mode"] == "half" and st["steps"] == [45]
    st = V.state(dict(QUEST3, vr=dict(QUEST3["vr"], hz=72, goal="half_room")), _vr())
    assert st["hz"] == 72 and st["target"] == 40 and st["hz_chosen"] and st["steps"] == [40]
    for bad in ("full", "", 45, True, None, ["half"]):          # anything else: the full refresh rate, as before
        st = V.state(dict(QUEST3, vr=dict(QUEST3["vr"], goal=bad)), _vr())
        assert st["target"] == 90 and st["hz"] == 90 and st["goal_mode"] is None and st["steps"] == [90, 80, 72, 36]
    # the chosen goal is the goal, whatever the PC can do: never swapped for another rate
    mdl = M.Model(90, 90, 3840, 2160, "nvidia", vr=st["model"])
    assert optimize.pick_target(mdl, 45, 16000, 0.8, steps=[45], current_low=80) == 45
    assert optimize.pick_target(mdl, 45, 16000, 0.8, steps=[45], current_low=20) == 45
    machine = rate.rate_machine(QUEST3)
    info = dict(QUEST3, vr=dict(QUEST3["vr"], goal="half_room"))
    fit = rate.rate_settings(info, _vr(), machine)
    said = " ".join(f["text"] for f in fit["findings"])
    assert fit["target_fps"] == 50 and "50 FPS, a little above half of the headset's 90 Hz" in said


def test_window_keeps_the_own_headset_goal_and_tests_for_it(tmp_path, monkeypatch):
    monkeypatch.setenv("DCSTUNE_VR_BENCH", "1")
    eng = _engine(tmp_path, monkeypatch)
    eng.info = dict(QUEST3, profiles=[{"name": "DCS"}])
    eng.set_headset("Meta Quest 3")
    h = eng.scorecard()["headset"]
    assert h["goal_mode"] == "" and h["goal_fps"] == 90 and [c["fps"] for c in h["goal_choices"]] == [90, 45, 50]
    assert "45 FPS" in eng.set_vr_goal("half")
    h = eng.scorecard()["headset"]
    assert h["hz"] == 90 and h["goal_mode"] == "half" and h["goal_fps"] == 45
    assert json.loads((tmp_path / "Config" / "dcstune-prefs.json").read_text())["vr_goal"] == "half"
    assert "aim for 36 FPS" in eng.set_headset_hz(72)             # half of the rate now picked
    assert [c["fps"] for c in eng.scorecard()["headset"]["goal_choices"]] == [72, 36, 40]
    log = []
    rep = eng.optimize(False, log.append)
    assert rep["vr"] and rep["target_fps"] == 36 and rep["goal_chosen"] == 36
    assert any("Your own goal: 36 FPS (for flying with motion smoothing at 72 Hz)" in line for line in log)
    assert "full refresh rate: 72 FPS" in eng.set_vr_goal("nonsense")
    assert eng.scorecard()["headset"]["goal_fps"] == 72


def test_window_keeps_the_scene_choice_and_tests_with_it(tmp_path, monkeypatch):
    # Issue #23: pick the map and aircraft for the test from what is installed.
    from dcstune import scenes, sysinfo
    eng = _engine(tmp_path, monkeypatch)
    dcs_root = tmp_path / "dcs"
    for folder in ("Mods/terrains/Syria", "Mods/aircraft/F14"):
        (dcs_root / folder).mkdir(parents=True)
    monkeypatch.setattr(sysinfo, "pick_install", lambda info: {"path": str(dcs_root)})
    card = eng.scorecard()["scene"]
    assert card["default"] and card["map"] == "caucasus" and card["aircraft"] == "Su-25T"
    assert [m["key"] for m in card["maps"]] == ["caucasus", "syria"]
    assert "F-14B over Syria (Beirut)" in eng.set_scene("syria", "F-14B")
    card = eng.scorecard()["scene"]
    assert not card["default"] and card["label"] == "F-14B over Syria (Beirut)"
    assert json.loads((tmp_path / "Config" / "dcstune-prefs.json").read_text())["bench_scene"] == ["syria", "F-14B"]
    log = []
    rep = eng.optimize(False, log.append)
    assert _FakeBench.made[-1].scene == ("syria", "F-14B")
    assert rep["scene"] == ["syria", "F-14B"] and rep["scene_label"] == "F-14B over Syria (Beirut)"
    assert any("Test scenes: F-14B over Syria (Beirut)" in line for line in log)
    from dcstune import report as R
    assert "flown with F-14B over Syria (Beirut)" in R._meta(rep)
    assert "standard scenes" in eng.set_scene("syria", "FA-18C_hornet")        # that module is not installed
    assert eng.scorecard()["scene"]["default"]
    assert "standard scenes" in eng.set_scene("nevada", "F-14B")               # that map is not installed
    rep = eng.optimize(False, log.append)
    assert _FakeBench.made[-1].scene is None and rep["scene"] is None and "flown with" not in R._meta(rep)


def test_dream_air_se_is_listed_with_its_own_panel():
    # Asked for on Discord, Nov 17. The SE has 2560 x 2560 per eye, not the Dream Air's 3840 x 3552.
    assert "Pimax Dream Air SE" in V.headset_names() and "Pimax Dream Air" in V.headset_names()
    se = V.state({"vr": {"runtime": "Pimax", "chosen": "Pimax Dream Air SE", "hz": 72}}, {"VR.enable": True})
    assert se["known"] and (se["eye_w"], se["eye_h"]) == (2560, 2560) and se["target"] == 72 and se["refresh"] == [72, 90]
    air = V.state({"vr": {"runtime": "Pimax", "chosen": "Pimax Dream Air"}}, {"VR.enable": True})
    assert (air["eye_w"], air["eye_h"]) == (3840, 3552)


def test_regular_build_lets_a_vr_player_choose_the_headset_test(tmp_path, monkeypatch):
    # Issue #10: the in-headset test is a choice in the regular build, off until the player picks it.
    monkeypatch.delenv("DCSTUNE_VR_BENCH", raising=False)
    eng = _engine(tmp_path, monkeypatch)
    eng.info = dict(QUEST3, profiles=[{"name": "DCS"}])
    sc = eng.scorecard()
    assert sc["vr"] and sc["vr_choice"] and not sc["vr_tested"] and not sc["vr_test_build"]
    rep = eng.optimize(False, QUIET)
    assert rep["vr_skipped"] and not _FakeBench.made[-1].vr                 # default: on the monitor, as before
    assert "in your headset" in eng.set_vr_test(True)
    assert json.loads((tmp_path / "Config" / "dcstune-prefs.json").read_text())["vr_in_headset"] is True
    sc = eng.scorecard()
    assert sc["vr_tested"] and sc["vr_choice"]
    rep = eng.optimize(False, QUIET)
    assert rep["vr"] and not rep["vr_skipped"] and _FakeBench.made[-1].vr
    for junk in (False, None, "1", 1):                                       # anything but True: the monitor
        assert "on the monitor" in eng.set_vr_test(junk)
        assert not eng.scorecard()["vr_tested"]
    monkeypatch.setenv("DCSTUNE_VR_BENCH", "1")                              # a VR test build: no choice, always the headset
    sc = eng.scorecard()
    assert sc["vr_tested"] and not sc["vr_choice"]
