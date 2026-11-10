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

    def optimize(self, full, log):
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
    assert "already the best match" in R.fragment({"before": rep["before"], "before_result": rep["before_result"]})


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
