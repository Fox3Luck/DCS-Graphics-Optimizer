import json
import shutil
from pathlib import Path

import pytest

from dcstune import model as M
from dcstune import optimize, rate
from dcstune.bench import BenchError, frame_stats, parse_result
from dcstune.optionslua import (Options, TrialSession, backup, format_value, list_backups,
                                parse_value, recover, sha256)

FIX = Path(__file__).parent / "fixtures"
FILES = sorted(FIX.glob("options.*.lua"))

# The test box as discovered on 2026-11-10.
INFO = {
    "cpu": "AMD Ryzen 7 9800X3D 8-Core Processor", "cores": 8, "ram_gb": 62,
    "gpus": [], "installs": [{"media": "SSD"}], "profiles": [],
    "gpu": {"name": "NVIDIA GeForce RTX 4080", "vram_mb": 16376, "width": 2560, "height": 1440, "refresh": 143},
}
WEAK = {
    "cpu": "Intel(R) Core(TM) i5-9600K CPU", "cores": 6, "ram_gb": 16, "gpus": [], "installs": [],
    "gpu": {"name": "NVIDIA GeForce GTX 1660 SUPER", "vram_mb": 6144, "width": 1920, "height": 1080, "refresh": 60},
}


# -- options.lua -------------------------------------------------------------
@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_roundtrip_is_byte_identical(path):
    assert Options.load(path).dumps() == path.read_bytes()


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_rewriting_every_value_unchanged_is_byte_identical(path):
    o = Options.load(path)
    for section in ("graphics", "VR"):
        for k, v in o.section(section).items():
            o.set(section, k, v)
    assert o.dumps() == path.read_bytes()


def test_set_changes_only_that_line():
    path = FIX / "options.DCS.lua"
    o = Options.load(path)
    assert o.get("graphics", "shadows") == 3 and o.get("graphics", "terrainTextures") == "min"
    o.update({"graphics.shadows": 4, "graphics.terrainTextures": "max", "graphics.sync": False,
              "graphics.forestDistanceFactor": 0.7})
    before, after = path.read_bytes().splitlines(), o.dumps().splitlines()
    assert len(before) == len(after)
    changed = [(a, b) for a, b in zip(before, after) if a != b]
    assert len(changed) == 4
    again = Options(o.dumps().decode())
    assert again.get("graphics", "shadows") == 4 and again.get("graphics", "sync") is False
    assert again.get("graphics", "forestDistanceFactor") == 0.7
    assert again.section("plugins") == Options.load(path).section("plugins")


def test_insert_missing_key_sorted_and_reparsable():
    o = Options.load(FIX / "options.DCS.lua")
    o.set("graphics", "SSAA", 1)
    text = o.dumps().decode()
    assert text.index('["SSAA"]') < text.index('["SSAO"]') > text.index('["MSAA"]')
    assert Options(text).get("graphics", "SSAA") == 1


def test_value_formats():
    for raw in ['"DLAA"', "0.66", "1.7777777777778", "true", "false", "3840", '""', "0"]:
        assert format_value(parse_value(raw)) == raw
    with pytest.raises(ValueError):
        parse_value("{")


def test_trial_session_restores_original(tmp_path):
    p = tmp_path / "options.lua"
    shutil.copy(FIX / "options.DCS.lua", p)
    original = sha256(p)
    with TrialSession(p) as s:
        s.write_trial({"graphics.shadows": 0})
        s.write_trial({"graphics.clouds": 0})           # trials never stack
        assert Options.load(p).get("graphics", "shadows") == 3
        assert Options.load(p).get("graphics", "clouds") == 0
    assert sha256(p) == original
    assert sorted(x.name for x in tmp_path.iterdir()) == ["options.lua"]


def test_recover_after_crash(tmp_path):
    p = tmp_path / "options.lua"
    shutil.copy(FIX / "options.DCS.lua", p)
    original = sha256(p)
    s = TrialSession(p)
    s.begin()
    s.write_trial({"graphics.shadows": 0})
    # ...process dies here; DCS may even have rewritten the file on exit
    p.write_bytes(p.read_bytes() + b"-- junk")
    assert recover(p) is True
    assert sha256(p) == original
    assert recover(p) is False


def test_backup_and_list(tmp_path):
    p = tmp_path / "options.lua"
    shutil.copy(FIX / "options.DCS.lua", p)
    b1, b2 = backup(p), backup(p)
    assert b1 != b2 and list_backups(p) == sorted([b1, b2])
    assert b1.read_bytes() == p.read_bytes()


# -- rating --------------------------------------------------------------------
def test_machine_rating():
    top, weak = rate.rate_machine(INFO), rate.rate_machine(WEAK)
    assert top["grade"] == "A" and not top["estimated"]
    assert weak["grade"] in "DF" and weak["score"] < top["score"]
    unknown = rate.rate_machine({**INFO, "gpu": {"name": "Mystery GPU 9000", "vram_mb": 8000}})
    assert unknown["estimated"]


def test_settings_rating_on_test_box_flags_wasted_headroom():
    flat = rate.flat_options(Options.load(FIX / "options.DCS.lua"))
    fit = rate.rate_settings(INFO, flat, rate.rate_machine(INFO))
    text = " ".join(f["text"] for f in fit["findings"])
    assert "Terrain textures" in text and "Textures are not on High" in text
    assert "3840x2160 but the desktop is 2560x1440" in text
    assert fit["basis"] == "estimated" and fit["target_fps"] == 120


def test_settings_rating_moves_with_load():
    machine = rate.rate_machine(WEAK)
    base = rate.flat_options(Options.load(FIX / "options.DCS.lua"))
    base.update({"graphics.width": 1920, "graphics.height": 1080})
    light = {**base, **{s["key"]: s["levels"][0]["v"] for s in M.SETTINGS}}
    heavy = {**base, **{s["key"]: s["levels"][-1]["v"] for s in M.SETTINGS},
             "graphics.Upscaling": "OFF", "graphics.AA": "MSAA", "graphics.MSAA": 2}
    r_light, r_heavy = (rate.rate_settings(WEAK, c, machine) for c in (light, heavy))
    assert r_light["fps"] > r_heavy["fps"]
    assert r_heavy["grade"] in "DF"
    measured = rate.rate_settings(WEAK, heavy, machine, {"p1_low_fps": 75, "avg_fps": 90, "vram_peak_mb": 4000})
    assert measured["basis"] == "measured" and measured["score"] > r_heavy["score"]


# -- model + optimizer -----------------------------------------------------------
def test_model_monotonic_and_calibration():
    mdl = M.Model(78, 100, 2560, 1440)
    ladder = M.upscale_ladder("nvidia")
    low = {s["key"]: s["levels"][0]["v"] for s in M.SETTINGS}
    high = {s["key"]: s["levels"][-1]["v"] for s in M.SETTINGS}
    assert mdl.frame_ms(high, ladder[0]) > mdl.frame_ms(low, ladder[0]) > mdl.frame_ms(low, ladder[-1])
    assert mdl.quality(high, ladder[0]) == pytest.approx(M.max_quality("nvidia"))
    mdl.calibrate(high, ladder[0], 50.0, 12000)
    assert mdl.fps(high, ladder[0]) == pytest.approx(50.0)
    assert mdl.vram_mb(high, ladder[0]) == pytest.approx(12000)


def test_level_index():
    s = next(x for x in M.SETTINGS if x["key"] == "graphics.forestDistanceFactor")
    assert M.level_index(s, 0.5) == 1 and M.level_index(s, 0.55) == 1 and M.level_index(s, 1) == 3
    civ = next(x for x in M.SETTINGS if x["key"] == "graphics.civTraffic")
    assert M.level_index(civ, "") == 0 and M.level_index(civ, "high") == 3


def test_choose_respects_budget_and_scales_with_hardware():
    strong, weak = M.Model(92, 100, 2560, 1440), M.Model(20, 45, 2560, 1440)
    cs, rs, fs = optimize.choose(strong, 120, 24000)
    cw, rw, fw = optimize.choose(weak, 60, 6000)
    assert fs and strong.fps(cs, rs) * 0.75 >= 120
    assert strong.quality(cs, rs) > weak.quality(cw, rw)
    assert weak.vram_mb(cw, rw) <= 6000 * optimize.VRAM_BUDGET or not fw
    if fw:
        assert weak.fps(cw, rw) * 0.75 >= 60


class FakePC:
    """Stands in for DCS: a 'true' machine the optimizer's model does not know."""

    def __init__(self, current, gpu, cpu, w=2560, h=1440, low_ratio=0.7):
        self.truth = M.Model(gpu, cpu, w, h)
        self.current, self.low_ratio, self.calls = current, low_ratio, []

    def measure(self, changes):
        cfg = dict(self.current)
        cfg.update(changes or {})
        self.calls.append(changes)
        rung = M.current_rung(cfg, "nvidia")
        fps = self.truth.fps(cfg, rung)
        return {"avg_fps": fps, "p1_low_fps": fps * self.low_ratio,
                "vram_peak_mb": self.truth.vram_mb(cfg, rung), "scenes": []}


def _current():
    return rate.flat_options(Options.load(FIX / "options.DCS.lua")) | {"graphics.width": 2560, "graphics.height": 1440}


@pytest.mark.parametrize("true_gpu,true_cpu", [(78, 100), (40, 60), (120, 100)])
def test_run_converges_when_model_is_wrong(true_gpu, true_cpu):
    cur = _current()
    pc = FakePC(cur, true_gpu, true_cpu)
    guess = M.Model(78, 100, 2560, 1440)          # what the tier table believes
    out = optimize.run(guess, cur, "nvidia", 120, 16376, pc.measure, log=lambda *_: None)
    assert pc.calls[0] is None and len(pc.calls) <= 1 + optimize.MAX_CONFIRM_RUNS
    rec = out["recommended"]
    if out["target_reached"] and rec:
        assert rec["result"]["p1_low_fps"] >= out["target_fps"] * optimize.HIT_MARGIN
        assert set(rec["changes"]) <= {s["key"] for s in M.SETTINGS} | {
            "graphics.Upscaling", "graphics.AA", "graphics.DLSS_PerfQuality", "graphics.MSAA", "graphics.Scaling"}
    never = set(M.TABLE["never_touch"])
    for h in out["history"]:
        assert not never & set(h["changes"])


def test_run_unreachable_target_recommends_fastest_seen():
    cur = _current()
    pc = FakePC(cur, 6, 20)
    out = optimize.run(M.Model(78, 100, 2560, 1440), cur, "nvidia", 120, 4096, pc.measure, log=lambda *_: None)
    assert not out["target_reached"] and out["recommended"] is not None
    assert out["recommended"]["result"]["p1_low_fps"] >= out["before"]["p1_low_fps"]


def test_full_mode_measures_each_setting_and_uses_costs():
    cur = _current()
    pc = FakePC(cur, 60, 80)
    mdl = M.Model(78, 100, 2560, 1440)
    out = optimize.run(mdl, cur, "nvidia", 120, 16376, pc.measure, full=True, log=lambda *_: None)
    assert set(mdl.measured) == {s["key"] for s in M.SETTINGS if s.get("measure") is not False}
    assert out["history"]


def test_describe_changes():
    cur = _current()
    lst = optimize.describe_changes(cur, {"graphics.shadows": 4, "graphics.textures": 1, "graphics.water": 0})
    assert [c["label"] for c in lst] == ["Shadows", "Water"]
    assert lst[0] == {"key": "graphics.shadows", "label": "Shadows", "from": "Medium", "to": "High", "direction": "up"}


# -- benchmark maths -------------------------------------------------------------
def test_frame_stats():
    ms = [10.0] * 990 + [50.0] * 10
    s = frame_stats(ms)
    assert s["p1_low_fps"] == 20.0 and s["stutters"] == 10 and s["frames"] == 1000
    assert s["avg_fps"] == pytest.approx(1000 / 10.4, abs=0.01)
    with pytest.raises(BenchError):
        frame_stats([10.0] * 5)


def test_parse_result_failure_is_reported():
    with pytest.raises(BenchError, match="unit not found"):
        parse_result({"ok": False, "reason": "unit not found: X", "scenes": []})
    r = parse_result({"ok": True, "scenes": [{"name": "city", "shot": "", "frame_ms": ["8.1"] * 100}]})
    assert r["scenes"][0]["name"] == "city" and optimize.summarise(r)["p1_low_fps"] == pytest.approx(123.46, abs=0.01)


# -- fixes after the first real session -------------------------------------------
def test_slider_values_between_levels_are_shown_truthfully():
    cur = _current() | {"graphics.clutterMaxDistance": 750, "graphics.forestDistanceFactor": 0.55}
    lst = {c["key"]: c for c in optimize.describe_changes(
        cur, {"graphics.clutterMaxDistance": 1500, "graphics.forestDistanceFactor": 0.5})}
    assert lst["graphics.clutterMaxDistance"]["from"] == "750 m" and lst["graphics.clutterMaxDistance"]["to"] == "1500 m"
    assert lst["graphics.clutterMaxDistance"]["direction"] == "up"
    assert lst["graphics.forestDistanceFactor"]["from"] == "55%" and lst["graphics.forestDistanceFactor"]["direction"] == "down"
    shadows = next(s for s in M.SETTINGS if s["key"] == "graphics.flatTerrainShadows")
    assert M.level_name(shadows, 0) == "Default"


def test_instant_scorecard_uses_last_benchmark(tmp_path):
    (tmp_path / "Config").mkdir()
    profile = {"path": str(tmp_path)}
    cur = _current()
    pc = FakePC(cur, 55, 80)                      # real PC is slower than the table says
    out = optimize.run(M.Model(78, 100, 2560, 1440), cur, "nvidia", 120, 16376, pc.measure, log=lambda *_: None)
    machine = rate.rate_machine(INFO)
    assert rate.load_calibration(profile, INFO, cur) is None
    rate.save_calibration(profile, INFO, cur, out["learned"])
    calib = rate.load_calibration(profile, INFO, cur)

    applied = cur | out["recommended"]["changes"]
    measured = out["recommended"]["result"]["p1_low_fps"]
    generic = rate.rate_settings(INFO, applied, machine)
    learned = rate.rate_settings(INFO, applied, machine, calibration=calib)
    assert learned["basis"] == "estimated from your last test"
    assert learned["fps"] == pytest.approx(measured, rel=0.03)
    assert abs(generic["fps"] - measured) > abs(learned["fps"] - measured)
    # a different GPU or resolution must not reuse it
    assert rate.load_calibration(profile, {**INFO, "gpu": {"name": "Other"}}, cur) is None
    assert rate.load_calibration(profile, INFO, cur | {"graphics.width": 1920}) is None


def test_full_mode_survives_a_failed_launch():
    cur = _current()
    pc = FakePC(cur, 60, 80)
    calls = {"n": 0}

    def flaky(changes):
        calls["n"] += 1
        if calls["n"] in (3, 4):
            raise RuntimeError("DCS did not finish")
        return pc.measure(changes)
    mdl = M.Model(78, 100, 2560, 1440)
    out = optimize.run(mdl, cur, "nvidia", 120, 16376, flaky, full=True, log=lambda *_: None)
    assert out["recommended"] or out["keep_current"]
    assert 0 < len(mdl.measured) < len(M.SETTINGS) + 1


def test_fast_cost_runs_use_their_own_baseline_and_skip_cheap_settings():
    cur = _current()
    pc = FakePC(cur, 60, 80)
    fast_calls = []

    def fast(changes):
        fast_calls.append(changes)
        r = pc.measure(changes)
        return {**r, "avg_fps": r["avg_fps"] * 1.1}      # a shorter window reads differently
    mdl = M.Model(78, 100, 2560, 1440)
    optimize.run(mdl, cur, "nvidia", 120, 16376, pc.measure, full=True, log=lambda *_: None, measure_fast=fast)
    assert fast_calls[0] is None                          # short baseline first
    touched = {k for c in fast_calls[1:] if c for k in c}
    assert fast_calls.count(None) >= 3                    # baseline re-checked along the way
    assert "graphics.anisotropy" not in touched and "graphics.shadows" in touched
    assert "graphics.anisotropy" not in mdl.measured


def test_session_screenshots_are_cleaned_up(tmp_path, monkeypatch):
    from dcstune import bench
    monkeypatch.setattr(bench, "dcs_running", lambda: False)
    cfg = tmp_path / "Config"; cfg.mkdir()
    shutil.copy(FIX / "options.DCS.lua", cfg / "options.lua")
    shots = tmp_path / "ScreenShots"; shots.mkdir()
    (shots / "my_own_screenshot.jpg").write_text("x")
    (shots / "dcstune_r01_city.jpg").write_text("older session")
    b = bench.Bench({"path": str(tmp_path), "name": "DCS", "options": str(cfg / "options.lua")}, tmp_path / "DCS.exe")
    with b:
        for n in ("r01_city", "r02_city", "r03_city"):
            (shots / f"dcstune_{b.session_id}{n}.jpg").write_text("x")
        b.keep_shots.add(f"dcstune_{b.session_id}r01_city")
    left = sorted(p.name for p in shots.iterdir())
    assert left == sorted(["my_own_screenshot.jpg", "dcstune_r01_city.jpg", f"dcstune_{b.session_id}r01_city.jpg"])
    assert not (tmp_path / "Scripts" / "Hooks" / "dcstune_bench.lua").exists()


def test_hardware_summary_and_overall():
    info = dict(INFO, installs=[{"media": "SSD", "version": "2.9.31.29434"}])
    rows = {r["label"]: r["value"] for r in rate.hardware_summary(info)}
    assert rows["Graphics card"] == "NVIDIA GeForce RTX 4080" and rows["Video memory"] == "16 GB"
    assert rows["Display"] == "2560 x 1440 at 143 Hz" and rows["DCS drive"] == "SSD"
    assert rows["Processor"].endswith("(8 cores)") and rows["DCS version"] == "2.9.31.29434"
    assert [r["label"] for r in rate.hardware_summary({})][:2] == ["Graphics card", "Video memory"]   # never crashes
    total = rate.overall({"score": 90}, {"score": 50, "basis": "measured"})
    assert total == {"score": 66, "grade": "C", "basis": "measured"}
    assert rate.overall({"score": 30}, {"score": 100, "basis": "estimated"})["score"] == 72


# -- lessons from the disturbed thorough run on 2026-11-10 ---------------------------
def test_never_recommends_worse_than_current():
    cur = _current()
    pc = FakePC(cur, 78, 100)
    n = {"i": 0}

    def measure(changes):
        n["i"] += 1
        r = pc.measure(changes)
        if changes:                     # every candidate measures badly (PC got busy)
            r = {**r, "avg_fps": r["avg_fps"] * 0.6, "p1_low_fps": 100.0}
        else:
            r = {**r, "p1_low_fps": 131.0}
        return r
    out = optimize.run(M.Model(78, 100, 2560, 1440), cur, "nvidia", 120, 16376, measure, log=lambda *_: None)
    assert out["keep_current"] and out["recommended"] is None and out["target_reached"]


def test_disturbed_cost_measurements_are_discarded():
    cur = _current()
    pc = FakePC(cur, 60, 80)
    n = {"i": 0}
    logs = []

    def measure(changes):
        n["i"] += 1
        r = pc.measure(changes)
        if 8 <= n["i"] <= 14:           # another program grabs the GPU for a while
            r = {**r, "avg_fps": r["avg_fps"] * 0.75}
        return r
    mdl = M.Model(78, 100, 2560, 1440)
    out = optimize.run(mdl, cur, "nvidia", 120, 16376, measure, full=True, log=logs.append)
    assert out["disturbed"] is True
    assert any("another program" in m for m in logs)
    measurable = {s["key"] for s in M.SETTINGS if s.get("measure") is not False}
    assert 0 < len(mdl.measured) < len(measurable)        # clean blocks kept, disturbed ones dropped
    for costs in mdl.measured.values():                    # nothing absurd survived
        assert all(costs[i] <= costs[j] + 0.3 for i in costs for j in costs if i < j)


def test_clean_full_run_is_not_flagged():
    cur = _current()
    pc = FakePC(cur, 60, 80)
    out = optimize.run(M.Model(78, 100, 2560, 1440), cur, "nvidia", 120, 16376, pc.measure, full=True, log=lambda *_: None)
    assert out["disturbed"] is False


def test_busy_gpu_refuses_to_start(tmp_path, monkeypatch):
    from dcstune import bench
    monkeypatch.setattr(bench, "dcs_running", lambda: False)
    monkeypatch.setattr(bench, "gpu_idle_check", lambda: (42.0, 8089.0))
    cfg = tmp_path / "Config"; cfg.mkdir()
    shutil.copy(FIX / "options.DCS.lua", cfg / "options.lua")
    before = sha256(cfg / "options.lua")
    b = bench.Bench({"path": str(tmp_path), "name": "DCS", "options": str(cfg / "options.lua")}, tmp_path / "DCS.exe")
    with pytest.raises(bench.BenchError, match="Another program is using your graphics card"):
        b.__enter__()
    assert sha256(cfg / "options.lua") == before and sorted(p.name for p in cfg.iterdir()) == ["options.lua"]
    b.allow_busy = True
    with b:
        assert b.other_vram_mb == 8089.0
