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
                                     headers={"X-DCSTune-Token": token})
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
