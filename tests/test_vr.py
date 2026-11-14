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
        "runtime": "SteamVR", "headset": None, "render_quality": None, "layers": 0, "quad_layer": True}
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

    def __init__(self, profile, exe, log=print, vr=False, vram_total_mb=0):
        self.vr, self.runs, self.keep_shots = vr, 0, set()
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
