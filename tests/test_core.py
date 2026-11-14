import json
import shutil
import time
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
    assert recover(p) == "restored"
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
    # the goal a Balanced test would pick on this PC (4K on an RTX 4080), not the screen's full 144 Hz
    assert fit["basis"] == "estimated" and fit["target_fps"] == 90


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


# -- benchmark math -------------------------------------------------------------
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
    assert r["scenes"][0]["name"] == "city" and optimize.summarize(r)["p1_low_fps"] == pytest.approx(123.46, abs=0.01)


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

    rec = out["recommended"]
    applied = cur | rec["changes"] if rec else cur
    measured = (rec["result"] if rec else out["before"])["p1_low_fps"]
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
    # a new before/recommended set replaces older sessions' leftovers; the player's own files stay
    assert left == sorted(["my_own_screenshot.jpg", f"dcstune_{b.session_id}r01_city.jpg"])
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


def test_video_memory_held_by_other_programs_is_warned_about(tmp_path, monkeypatch):
    """A local AI model holding video memory does not stop the test, but the player is told."""
    from dcstune import bench, report as R
    assert bench.other_vram_high(7200, 16376) and not bench.other_vram_high(2100, 16376)
    assert bench.other_vram_high(2600, 8192) and not bench.other_vram_high(2600, 16376)    # a share of big cards
    assert bench.other_vram_high(2600) and not bench.other_vram_high(0)                    # card size unknown
    monkeypatch.setattr(bench, "dcs_running", lambda: False)
    cfg = tmp_path / "Config"; cfg.mkdir()
    shutil.copy(FIX / "options.DCS.lua", cfg / "options.lua")
    prof = {"path": str(tmp_path), "name": "DCS", "options": str(cfg / "options.lua")}
    for other, warned in ((7200.0, True), (2100.0, False)):
        monkeypatch.setattr(bench, "gpu_idle_check", lambda: (1.0, other))
        said = []
        with bench.Bench(prof, tmp_path / "DCS.exe", log=said.append, vram_total_mb=16376):
            pass
        assert any("other programs are using 7.0 GB of 16 GB" in m for m in said) is warned


# -- no-restart batches ---------------------------------------------------------------
def _batch_fn(pc, record, disturb=lambda n, i: 1.0, fail=()):
    def batch(changes_list):
        n = len(record)
        record.append(changes_list)
        if n in fail:
            raise RuntimeError("DCS crashed")
        return [{"avg_fps": pc.measure(c)["avg_fps"] * disturb(n, i)} for i, c in enumerate(changes_list)]
    return batch


def test_batches_measure_everything_except_restart_settings():
    cur = _current()
    pc, batches, singles = FakePC(cur, 60, 80), [], []

    def fast(c):
        singles.append(c)
        return pc.measure(c)
    mdl = M.Model(78, 100, 2560, 1440)
    out = optimize.run(mdl, cur, "nvidia", 120, 16376, pc.measure, full=True, log=lambda *_: None,
                       measure_fast=fast, measure_batch=_batch_fn(pc, batches))
    assert out["disturbed"] is False
    in_batches = {k for b in batches for c in b if c for k in c}
    in_singles = {k for c in singles if c for k in c}
    assert in_singles == {s["key"] for s in M.SETTINGS if s.get("restart")}
    assert in_singles == {"graphics.terrainTextures", "graphics.textures"} and "graphics.visibRange" in in_batches
    assert not in_batches & in_singles and "graphics.shadows" in in_batches
    for b in batches:
        assert b[0] is None and b[-1] is None and len(b) <= optimize.BATCH_SIZE + 2
    measurable = {s["key"] for s in M.SETTINGS if s.get("measure") is not False}
    assert set(mdl.measured) == measurable
    # the measured cost equals the true cost on the fake PC
    shadows = next(s for s in M.SETTINGS if s["key"] == "graphics.shadows")
    rung = M.current_rung(cur, "nvidia")
    true = pc.truth.frame_ms(cur | {"graphics.shadows": 4}, rung) - pc.truth.frame_ms(cur | {"graphics.shadows": 0}, rung)
    assert mdl.measured["graphics.shadows"][len(shadows["levels"]) - 1] == pytest.approx(true, rel=0.02)


def test_disturbed_or_failed_batch_is_discarded_but_others_kept(monkeypatch):
    monkeypatch.setattr(optimize, "BATCH_SIZE", 4)
    cur = _current()
    pc, batches, logs = FakePC(cur, 60, 80), [], []
    slow_tail = lambda n, i: 0.8 if (n == 0 and i >= 4) else 1.0     # PC slows mid-way through batch 0
    mdl = M.Model(78, 100, 2560, 1440)
    out = optimize.run(mdl, cur, "nvidia", 120, 16376, pc.measure, full=True, log=logs.append,
                       measure_batch=_batch_fn(pc, batches, slow_tail))
    assert out["disturbed"] is True and any("speed changed during this run" in m for m in logs)
    first_batch_keys = {k for c in batches[0] if c for k in c}
    assert len(batches) >= 2 and mdl.measured                      # later batch still counted
    kept = set(mdl.measured)
    later_only = {k for b in batches[1:] for c in b if c for k in c} - first_batch_keys
    assert later_only <= kept and not (first_batch_keys - later_only) & kept

    mdl2, batches2 = M.Model(78, 100, 2560, 1440), []
    out2 = optimize.run(mdl2, cur, "nvidia", 120, 16376, pc.measure, full=True, log=lambda *_: None,
                        measure_batch=_batch_fn(pc, batches2, fail={0}))
    assert out2["disturbed"] is True and (out2["recommended"] or out2["keep_current"])


def test_bench_batch_builds_self_resetting_trials(tmp_path, monkeypatch):
    from dcstune import bench
    monkeypatch.setattr(bench, "dcs_running", lambda: False)
    monkeypatch.setattr(bench, "gpu_idle_check", lambda: (1.0, 2000.0))
    cfg = tmp_path / "Config"; cfg.mkdir()
    shutil.copy(FIX / "options.DCS.lua", cfg / "options.lua")
    b = bench.Bench({"path": str(tmp_path), "name": "DCS", "options": str(cfg / "options.lua")}, tmp_path / "DCS.exe")
    seen = {}

    def fake_run_trials(trials, short=True, screenshots=True):
        seen.update(trials=trials, screenshots=screenshots)
        return [{"avg_fps": 100.0 + n} for n, _ in enumerate(trials)]
    with b:
        monkeypatch.setattr(b, "run_trials", fake_run_trials)
        out = b.measure_batch([None, {"graphics.shadows": 0}, {"graphics.clouds": 0}, None])
    # the warm-up trial's result is dropped
    assert [r["avg_fps"] for r in out] == [101.0, 102.0, 103.0, 104.0] and seen["screenshots"] is False
    sets = [t["set"] for t in seen["trials"]]
    # fixture values: shadows 3, clouds 3. Every trial names both, so each undoes the one before.
    assert sets == [{"shadows": 3, "clouds": 3}, {"shadows": 3, "clouds": 3}, {"shadows": 0, "clouds": 3},
                    {"shadows": 3, "clouds": 0}, {"shadows": 3, "clouds": 3}]
    assert [t["settle_sec"] for t in seen["trials"]] == [20, 10, 10, 10, 10]   # equal waits for all measured trials


def test_marginal_candidate_does_not_replace_settings_that_already_hold_the_goal():
    """Clean thorough run 2026-11-10: current 138 FPS lows (goal 120); the candidate looked
    slightly better on paper but measured 118. That is not a recommendation."""
    cur = _current()
    pc = FakePC(cur, 78, 100)

    def measure(changes):
        r = pc.measure(changes)
        return {**r, "p1_low_fps": 118.0 if changes else 138.0}
    out = optimize.run(M.Model(78, 100, 2560, 1440), cur, "nvidia", 120, 16376, measure, log=lambda *_: None)
    assert out["keep_current"] and out["recommended"] is None and out["target_reached"]


def test_scorecard_shows_measured_numbers_for_settings_that_were_tested(tmp_path):
    (tmp_path / "Config").mkdir()
    profile = {"path": str(tmp_path)}
    cur = _current()
    machine = rate.rate_machine(INFO)
    rec = cur | {"graphics.shadows": 4, "graphics.forestDistanceFactor": 1}
    learned = {"calibration": 1.0, "vram_offset": 0, "low_ratio": 0.7, "measured": {}}
    rate.save_calibration(profile, INFO, cur, learned, [
        (cur, {"p1_low_fps": 166, "avg_fps": 260, "vram_peak_mb": 6334}),
        (rec, {"p1_low_fps": 123, "avg_fps": 171, "vram_peak_mb": 7901})])
    # 1 and 1.0 are the same setting once DCS or the tool has rewritten the file
    applied = rec | {"graphics.forestDistanceFactor": 1.0}
    fit = rate.rate_settings(INFO, applied, machine, calibration=rate.load_calibration(profile, INFO, applied))
    assert fit["basis"] == "measured in your last test" and fit["fps"] == 123 and fit["vram_mb"] == 7901
    other = rec | {"graphics.shadows": 2}
    assert rate.rate_settings(INFO, other, machine, calibration=rate.load_calibration(profile, INFO, other))["basis"] \
        == "estimated from your last test"
    # a later test keeps earlier results
    rate.save_calibration(profile, INFO, cur, learned, [(other, {"p1_low_fps": 140, "avg_fps": 190})])
    assert len(rate.load_calibration(profile, INFO, cur)["results"]) == 3


# -- the hook cannot be left behind or driven by a stray file --------------------------
def _bench(tmp_path, monkeypatch):
    from dcstune import bench
    monkeypatch.setattr(bench, "dcs_running", lambda: False)
    monkeypatch.setattr(bench, "gpu_idle_check", lambda: (0.0, 0.0))
    cfg = tmp_path / "Config"; cfg.mkdir()
    shutil.copy(FIX / "options.DCS.lua", cfg / "options.lua")
    return bench, bench.Bench({"path": str(tmp_path), "name": "DCS", "options": str(cfg / "options.lua")},
                              tmp_path / "DCS.exe")


def test_each_installed_hook_has_its_own_key_and_directive_carries_it(tmp_path, monkeypatch):
    bench, b = _bench(tmp_path, monkeypatch)
    hook = tmp_path / "Scripts" / "Hooks" / "dcstune_bench.lua"
    seen = []

    class Proc:
        def __init__(self, args, cwd): seen.append(dict(json.loads(b.directive.read_text()), hook=hook.read_text()))
        def wait(self, timeout=None): b.result.write_text('{"ok":true}')
    monkeypatch.setattr(bench.subprocess, "Popen", Proc)
    monkeypatch.setattr(bench.time, "sleep", lambda s: None)
    with b:
        text = hook.read_text()
        assert bench.KEY_MARK not in text and f'"{b.key}"' in text and len(b.key) == 32
        b._launch(None, {"tag": "x"}, True, 100)
        b._launch(None, {"tag": "y"}, True, 100)
    d1, d2 = seen
    assert d1["key"] != d2["key"] and d2["key"] == b.key                         # new hook and key for every DCS start
    assert f'"{d1["key"]}"' in d1["hook"] and f'"{d2["key"]}"' in d2["hook"]
    assert len(d1["password"]) == 32 and d1["password"] != d2["password"]       # new for every DCS start
    assert 20000 <= d1["port"] < 60000 and d1["mission"] == str(b.mission_dst)
    assert 0 < d1["not_after"] - time.time() <= bench.DIRECTIVE_VALID_SEC
    assert not hook.exists()
    first = b.key
    with b:
        assert b.key != first


def test_leftovers_of_an_interrupted_test_are_removed_at_start(tmp_path, monkeypatch):
    bench, b = _bench(tmp_path, monkeypatch)
    b.__enter__()                                   # ...and the program is killed here
    b.directive.write_text("{}")
    assert b.hook_dst.exists() and b.mission_dst.exists()
    assert sorted(bench.remove_leftovers(tmp_path)) == ["dcstune_bench.lua", "dcstune_bench.miz", "dcstune_directive.json"]
    assert not b.hook_dst.exists() and not b.mission_dst.exists() and not b.directive.exists()
    assert bench.remove_leftovers(tmp_path) == []


def test_primary_display_replaces_the_cards_own_figures():
    """Two monitors: the card reported the second one (1440p 144 Hz) while DCS runs on the
    primary (4K 60 Hz). The primary one must set the resolution and the frame-rate goal."""
    from dcstune.sysinfo import normalize
    raw = {"gpus": [{"name": "NVIDIA GeForce RTX 4080", "vram_mb": 16376, "width": 2560, "height": 1440, "refresh": 143}],
           "display": {"width": 3840, "height": 2160, "refresh": 60, "count": 2}}
    g = normalize(raw)["gpu"]
    assert (g["width"], g["height"], g["refresh"]) == (3840, 2160, 60) and g["vram_mb"] == 16376
    assert raw["gpus"][0]["width"] == 2560                      # the input is not altered
    for missing in (None, {}, {"width": 0, "height": 0}):       # no answer from Windows: keep the card's figures
        g = normalize(dict(raw, display=missing))["gpu"]
        assert (g["width"], g["height"], g["refresh"]) == (2560, 1440, 143)
    assert normalize(dict(raw, display={"width": 3840, "height": 2160, "refresh": None}))["gpu"]["refresh"] == 143


# -- VR: monitor numbers must never be reported as headset numbers ----------------------
# Lines DCS 2.9.31 really wrote on 2026-11-13: first with no headset behind the VR software,
# then with a (simulated) headset that accepted the picture.
LOG_NO_HEADSET = """INFO    VISUALIZER (Main): [00:57:49.896][Info   ] OpenXR: Instance RuntimeName=Pimax OpenXR RuntimeVersion=0.1.0
WARNING VISUALIZER (Main): [00:57:49.897][Warning] OpenXR: waiting for HMD to warm up...
ERROR   VISUALIZER (Main): OpenXR failure XrResult failure [XR_ERROR_FORM_FACTOR_UNAVAILABLE]
ERROR   VISUALIZER (Main): OpenXR exception: XrResult failure [XR_ERROR_FORM_FACTOR_UNAVAILABLE]
"""
LOG_IN_HEADSET = """INFO    VISUALIZER (Main): [01:01:01.783][Info   ] OpenXR: Instance RuntimeName=SteamVR/OpenXR RuntimeVersion=2.18.4
INFO    VISUALIZER (21588): [01:01:09.068][Info   ] OpenXR: Creating swapchain for view 0 with dimensions Width=2880 Height=2880 SampleCount=1
INFO    VISUALIZER (21588): [01:01:09.070][Info   ] OpenXR: Creating swapchain for view 1 with dimensions Width=2880 Height=2880 SampleCount=1
"""


def test_vr_run_that_fell_back_to_the_monitor_is_refused(tmp_path, monkeypatch):
    bench, b = _bench(tmp_path, monkeypatch)
    assert bench.vr_started(LOG_IN_HEADSET) and not bench.vr_started(LOG_NO_HEADSET) and not bench.vr_started("")
    b.vr = True
    logs = tmp_path / "Logs"; logs.mkdir()

    class Proc:
        def __init__(self, args, cwd): assert ("--force_enable_VR" in args) is b.vr
        def wait(self, timeout=None): b.result.write_text('{"ok":true}')       # DCS finished - on the monitor
    monkeypatch.setattr(bench.subprocess, "Popen", Proc)
    monkeypatch.setattr(bench.time, "sleep", lambda s: None)
    (logs / "dcs.log").write_text(LOG_NO_HEADSET)
    with b:
        with pytest.raises(bench.BenchError, match="ran on the monitor instead"):
            b._launch(None, {"tag": "x"}, True, 100)
        assert not b.result.exists() and not b.directive.exists()
        assert (tmp_path / "Config" / "dcstune-last-failure.log").read_text() == LOG_NO_HEADSET
        (logs / "dcs.log").write_text(LOG_IN_HEADSET)
        assert b._launch(None, {"tag": "y"}, True, 100)[0] == {"ok": True}
        (logs / "dcs.log").unlink()                                            # no log to prove it: refuse
        with pytest.raises(bench.BenchError, match="ran on the monitor instead"):
            b._launch(None, {"tag": "z"}, True, 100)
    b.vr = False                                                               # monitor tests never look at it
    with b:
        assert b._launch(None, {"tag": "m"}, True, 100)[0] == {"ok": True}


def test_headset_software_is_not_counted_as_another_program(tmp_path, monkeypatch):
    from dcstune import bench
    # 2026-11-13: 3.6 GB in use before DCS started, 1.5 GB of it SteamVR - no warning in VR, a warning on the monitor
    assert bench.other_vram_high(3600, 16376) and not bench.other_vram_high(3600, 16376, vr=True)
    assert bench.other_vram_high(7200, 16376, vr=True)                         # an AI model on top still warns
    monkeypatch.setattr(bench, "dcs_running", lambda: False)
    monkeypatch.setattr(bench, "gpu_idle_check", lambda: (1.0, 3600.0))
    cfg = tmp_path / "Config"; cfg.mkdir()
    shutil.copy(FIX / "options.DCS.lua", cfg / "options.lua")
    prof = {"path": str(tmp_path), "name": "DCS", "options": str(cfg / "options.lua")}
    for vr in (True, False):
        said = []
        with bench.Bench(prof, tmp_path / "DCS.exe", log=said.append, vr=vr, vram_total_mb=16376):
            pass
        assert any("other programs are using" in m for m in said) is (not vr)
