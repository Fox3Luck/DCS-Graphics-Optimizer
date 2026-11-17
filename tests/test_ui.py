# DCS Graphics Optimizer - Fox3 Managed Solutions Inc.
# Created 2026-11-10. Tests for the window's local page and its buttons.
import json
import shutil
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from dcstune import bench, optimize, ui
from dcstune.optionslua import Options, sha256
from test_core import FIX, INFO, FakePC, _current


class TmpEngine(ui.Engine):
    """Real Engine logic on a copy of the test box's options.lua; DCS replaced by FakePC."""

    def __init__(self, root: Path):
        cfg = root / "Config"
        cfg.mkdir()
        shutil.copy(FIX / "options.DCS.lua", cfg / "options.lua")
        self.info = dict(INFO, profiles=[{"name": "DCS"}])
        self.profile = {"name": "DCS", "path": str(root), "options": str(cfg / "options.lua")}
        self.recovered = False

    def optimize(self, full, log, mode="balanced"):
        from dcstune import model as M, rate
        flat = self._flat()
        pc = FakePC(flat, 70, 95, 3840, 2160)
        machine = rate.rate_machine(self.info)
        mdl = M.Model(machine["gpu_score"], machine["cpu_score"], 3840, 2160)
        out = optimize.run(mdl, flat, "nvidia", 120, 16376, pc.measure, full=full, log=log)
        rec = out["recommended"]
        after = dict(flat); after.update(rec["changes"])
        report = {"target_fps": out["target_fps"], "target_reached": out["target_reached"],
                  "before": rate.rate_settings(self.info, flat, machine, out["before"], out["target_fps"]),
                  "after": rate.rate_settings(self.info, after, machine, rec["result"], out["target_fps"]),
                  "before_result": ui._slim(out["before"]), "after_result": ui._slim(rec["result"]),
                  "changes": rec["changes"], "change_list": optimize.describe_changes(flat, rec["changes"])}
        self.report_path().write_text(json.dumps(report))
        return report


@pytest.fixture
def served(tmp_path, monkeypatch):
    monkeypatch.setattr(bench, "dcs_running", lambda: False)
    app = ui.App(lambda: TmpEngine(tmp_path))
    server = ui.make_server(app)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(path, body=None, token=app.token):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"X-DCSGO-Token": token})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
    yield app, call, tmp_path / "Config" / "options.lua"
    server.shutdown()


def test_token_required(served):
    app, call, _ = served
    assert call("/api/scorecard", token="wrong")[0] == 403
    assert call("/api/apply", {}, token="")[0] == 403
    assert call("/?t=wrong")[0] == 403
    status, page = call("/?t=" + app.token)
    assert status == 200 and app.token.encode() in page and b"__TOKEN__" not in page


def test_scorecard_optimize_apply_undo(served):
    app, call, options = served
    status, raw = call("/api/scorecard")      # first call builds the engine (and the temp profile)
    original = sha256(options)
    sc = json.loads(raw)
    assert status == 200 and sc["machine"]["grade"] == "A" and sc["can_undo"] is False and sc["report"] is None
    assert sc["overall"]["grade"] in "AB" and sc["hardware"][0]["value"] == "NVIDIA GeForce RTX 4080"
    assert json.loads(call("/api/apply", {})[1])["error"].startswith("There is no recommendation")

    assert call("/api/optimize", {"full": False})[0] == 200
    for _ in range(100):
        job = json.loads(call("/api/job")[1])
        if job["state"] != "running":
            break
        time.sleep(0.05)
    assert job["state"] == "done", job
    assert job["log"][0].startswith("Measuring your current settings")
    assert sha256(options) == original                      # nothing changed before Apply
    report = json.loads(call("/api/scorecard")[1])["report"]
    assert report["change_list"] and report["after"]["score"] >= report["before"]["score"]

    assert call("/api/apply", {})[0] == 200
    applied = Options.load(options)
    for dotted, v in report["changes"].items():
        section, key = dotted.split(".", 1)
        assert applied.get(section, key) == v
    assert applied.get("graphics", "width") == 3840 and applied.section("plugins") == Options.load(FIX / "options.DCS.lua").section("plugins")
    assert json.loads(call("/api/scorecard")[1])["can_undo"] is True

    assert call("/api/undo", {})[0] == 200
    assert sha256(options) == original
    assert json.loads(call("/api/undo", {})[1])["error"].startswith("No earlier settings")


def test_apply_refused_while_dcs_runs(served, monkeypatch):
    app, call, options = served
    app.engine.report_path().write_text(json.dumps({"changes": {"graphics.shadows": 0}}))
    monkeypatch.setattr(bench, "dcs_running", lambda: True)
    status, raw = call("/api/apply", {})
    assert status == 400 and "Close DCS first" in json.loads(raw)["error"]
    assert Options.load(options).get("graphics", "shadows") == 3


# -- the report a customer sees ----------------------------------------------------
def _sample_report(tmp_path):
    from dcstune import model as M, rate, report as R
    eng = TmpEngine(tmp_path)
    flat = eng._flat()
    machine = rate.rate_machine(eng.info)
    mdl = M.Model(machine["gpu_score"], machine["cpu_score"], 3840, 2160)
    mdl.record_cost("graphics.shadows", 4, 0.4)
    changes = {"graphics.DLSS_PerfQuality": 1, "graphics.shadows": 4, "graphics.textures": 2}
    after = dict(flat) | changes
    B = {"avg_fps": 260, "p1_low_fps": 166, "vram_peak_mb": 6334}
    A = {"avg_fps": 171, "p1_low_fps": 123, "vram_peak_mb": 7901}
    rep = {"created": "2026-11-10 03:08", "kind": "Thorough test", "duration_min": 37, "runs": 10,
           "target_fps": 120, "target_reached": True, "machine": machine,
           "hardware": rate.hardware_summary(eng.info),
           "before": rate.rate_settings(eng.info, flat, machine, B, 120), "before_result": B,
           "after": rate.rate_settings(eng.info, after, machine, A, 120), "after_result": A,
           "changes": changes, "change_list": optimize.describe_changes(flat, changes, "nvidia", mdl, 1000 / 260),
           "costs": optimize.measured_costs(mdl, 1000 / 260),
           "shots": [{"scene": "city", "before": "a_city.png", "after": "b_city.png"}]}
    rep["overall_before"], rep["overall_after"] = rate.overall(machine, rep["before"]), rate.overall(machine, rep["after"])
    return eng, rep, R


def test_report_reads_like_plain_language(tmp_path):
    eng, rep, R = _sample_report(tmp_path)
    first = rep["change_list"][0]
    assert first["label"] == "Upscaling and anti-aliasing" and (first["from"], first["to"]) == ("DLSS Balanced", "DLSS Quality")
    assert not any("DLSS_PerfQuality" in str(c["label"]) for c in rep["change_list"])
    shadows = next(c for c in rep["change_list"] if c["key"] == "graphics.shadows")
    assert shadows["cost_basis"] == "measured" and shadows["why"] and "measured" in R.cost_text(shadows)
    html = R.page(rep)
    for want in ("Thorough test", "37 minutes", "DCS started 10 times", "DLSS Balanced", "6.2 GB", "7.7 GB",
                 "This tool does not change this", 'src="a_city.png"', "City pass", "What each setting costs"):
        assert want in html, want
    assert "DLSS_PerfQuality" not in html and html.count("Holds about") == 0
    assert 'src="/x/a_city.png"' in R.fragment(rep, lambda n: "/x/" + n)
    kept = R.fragment({"before": rep["after"], "before_result": rep["after_result"]})
    assert "already the best match" in kept and "<th>Your settings</th>" in kept and "This tool does not change this" in kept


def test_report_folder_apply_keeps_report_and_files_are_guarded(served):
    app, call, options = served
    call("/api/scorecard")
    eng = app.engine
    shots = Path(eng.profile["path"]) / "ScreenShots"
    shots.mkdir()
    (shots / "dcstune_1r01_city.png").write_bytes(b"png-before")
    (shots / "dcstune_1r02_city.jpg").write_bytes(b"jpg-after")
    (Path(eng.profile["path"]) / "x").mkdir()
    _, rep, _ = _sample_report(Path(eng.profile["path"]) / "x")
    rep.pop("shots")
    out = {"before": {"scenes": [{"name": "city", "shot": "dcstune_1r01_city"}]},
           "recommended": {"result": {"raw": {"scenes": [{"name": "city", "shot": "dcstune_1r02_city"}]}}}}
    eng._save_report_folder(rep, out)
    eng.report_path().write_text(json.dumps(rep))
    folder = eng.reports_dir() / rep["dir"]
    assert (folder / "report.html").is_file() and not list(shots.iterdir())
    assert rep["shots"] == [{"scene": "city", "before": "dcstune_1r01_city.png", "after": "dcstune_1r02_city.jpg"}]

    sc = json.loads(call("/api/scorecard")[1])
    assert "/report-file/dcstune_1r01_city.png?t=" + app.token in sc["report_html"]
    assert call("/report-file/dcstune_1r01_city.png?t=" + app.token) == (200, b"png-before")
    assert call("/report-file/dcstune_1r01_city.png?t=nope")[0] == 404
    assert call("/report-file/report.html?t=" + app.token)[0] == 404          # images only
    assert call("/report-file/..%5C..%5CConfig%5Coptions.lua?t=" + app.token)[0] == 404

    assert call("/api/apply", {})[0] == 200
    sc = json.loads(call("/api/scorecard")[1])
    assert sc["report"]["applied"] and "were applied on" in sc["report_html"]
    assert "already applied" in json.loads(call("/api/apply", {})[1])["error"]
    assert call("/api/undo", {})[0] == 200
    assert "applied" not in json.loads(call("/api/scorecard")[1])["report"]


def test_goal_and_refresh_rate_buttons(served):
    # Issues #45 and #40: the player's own frame-rate goal and headset refresh rate, set from the window.
    app, call, _ = served
    sc = json.loads(call("/api/scorecard")[1])
    assert sc["goal"] == {"chosen": None, "choices": [30, 40, 45, 50, 60, 75, 90, 100, 120], "auto": sc["goal"]["auto"]}
    status, body = call("/api/goal", {"fps": 45})
    assert status == 200 and "45 FPS" in json.loads(body)["message"]
    sc = json.loads(call("/api/scorecard")[1])
    assert sc["goal"]["chosen"] == 45 and sc["settings"]["target_fps"] == 45
    for junk in ("45", 46, None, {"x": 1}):                       # anything else means automatic
        assert "automatic" in json.loads(call("/api/goal", {"fps": junk})[1])["message"]
        assert json.loads(call("/api/scorecard")[1])["goal"]["chosen"] is None
    assert "automatic" in json.loads(call("/api/headset-hz", {"hz": 72})[1])["message"]   # VR is off here
    with app.lock:
        app.job["state"] = "running"
    status, body = call("/api/goal", {"fps": 30})
    assert status != 200 and b"A test is running" in body
    with app.lock:
        app.job["state"] = "idle"
    page = call("/?t=" + app.token)[1]
    assert b'id="goal-pick"' in page and b'id="hz-pick"' in page


def test_unticked_changes_are_left_alone(served):
    """#24: the player can untick changes before Apply; those settings stay as they were."""
    app, call, options = served
    call("/api/scorecard")
    original = Options.load(options)
    changes = {"graphics.DLSS_PerfQuality": 1, "graphics.Upscaling": "DLSS", "graphics.shadows": 4, "graphics.textures": 2}
    rows = [{"key": "upscaling", "label": "Upscaling and anti-aliasing", "from": "a", "to": "b"},
            {"key": "graphics.shadows", "label": "Shadows", "from": "a", "to": "b"},
            {"key": "graphics.textures", "label": "Textures", "from": "a", "to": "b"}]
    app.engine.report_path().write_text(json.dumps({"before": {"grade": "B", "score": 70}, "after": {"grade": "A", "score": 90}, "changes": changes,
                                                    "change_list": rows}))
    status, raw = call("/api/apply", {"skip": ["graphics.shadows", "upscaling", "graphics.bogus"]})
    assert status == 200 and "leaving 2 settings as you had them" in json.loads(raw)["message"]
    after = Options.load(options)
    assert after.get("graphics", "textures") == 2
    for key in ("shadows", "DLSS_PerfQuality", "Upscaling"):
        assert after.get("graphics", key) == original.get("graphics", key), key
    sc = json.loads(call("/api/scorecard")[1])
    assert sc["report"]["skipped"] == ["graphics.shadows", "upscaling"]
    assert "not applied, kept as it was" in sc["report_html"] and 'class="pick"' not in sc["report_html"]
    assert call("/api/undo", {})[0] == 200 and "skipped" not in json.loads(call("/api/scorecard")[1])["report"]


def test_untick_everything_applies_nothing(served):
    app, call, options = served
    call("/api/scorecard")
    before = sha256(options)
    app.engine.report_path().write_text(json.dumps({"changes": {"graphics.shadows": 0},
                                                    "change_list": [{"key": "graphics.shadows", "label": "Shadows"}]}))
    status, raw = call("/api/apply", {"skip": ["graphics.shadows"]})
    assert status == 400 and "nothing to apply" in json.loads(raw)["error"] and sha256(options) == before


def test_window_offers_tick_boxes_and_fps_numbers(tmp_path):
    eng, rep, R = _sample_report(tmp_path)
    win, saved = R.fragment(rep, pick=True), R.page(rep)
    assert win.count('class="pick"') == len(rep["change_list"]) and 'class="pick"' not in saved
    shadows = next(c for c in rep["change_list"] if c["key"] == "graphics.shadows")
    text = R.cost_text(shadows, 260)
    assert " FPS" in text and text.split(", ")[1].startswith("-"), text
    guess = next(c for c in rep["change_list"] if c.get("cost_basis") == "estimate")
    assert "FPS" not in R.cost_text(guess, 260)          # estimates are not turned into FPS
    one = dict(rep, change_list=[guess], before_result={"avg_fps": 96}, after_result={"avg_fps": 161})
    assert "Measured: 96 to 161 FPS average" in R.fragment(one)
    assert "average frame rate of 260 FPS" in win
    assert 'class="pick"' not in R.fragment(dict(rep, applied="2026-11-16 20:00"), pick=True)


def test_report_says_what_limits_the_frame_rate(tmp_path):
    """#31: from the graphics card load while each scene was timed."""
    eng, rep, R = _sample_report(tmp_path)
    gpu = dict(rep, before_result={"avg_fps": 120, "scenes": [
        {"name": "city", "avg_fps": 110, "p1_low_fps": 80, "gpu_busy": 97},
        {"name": "airfield", "avg_fps": 130, "p1_low_fps": 95, "gpu_busy": 55}]})
    html = R.fragment(gpu)
    assert "What limits your frame rate" in html and "97%" in html and "processor</td>" in html
    assert "slowest scene (city pass) your graphics card is working flat out" in html
    cpu = dict(gpu, before_result={"scenes": [{"name": "airfield", "p1_low_fps": 60, "gpu_busy": 50}]})
    assert "waiting for the processor" in R.fragment(cpu)
    assert "What limits" not in R.fragment(dict(rep, before_result={"scenes": [{"name": "city"}]}))


def test_scene_load_comes_from_samples_inside_the_scene():
    from dcstune import bench
    g = bench.GpuSampler()
    g.samples = [(100, 10), (101, 99), (102, 98), (103, 97), (104, 96), (110, 5)]
    assert g.busy_between(101, 103) == 98 and g.busy_between(200, 230) is None
    raw = {"ok": True, "scenes": [{"name": "city", "w0": 101, "w1": 103, "frame_ms": [10.0] * 40}]}
    sc = bench.parse_result(raw)["scenes"][0]
    assert (sc["w0"], sc["w1"]) == (101, 103)
