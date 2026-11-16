# DCS Graphics Optimizer - Fox3 Managed Solutions Inc.
# Created 2026-11-14. Tests for the failure-log extract.
"""The failure-log extract shown when a test fails (made-up log; no player data in the repo)."""
import json
import time

import pytest

from dcstune import failurelog, ui
from test_core import INFO

SAVED = r"C:\Users\Pilot Jane\Saved Games\DCS"
DCS = r"E:\Games\DCS World"
LOG = "\n".join([
    "=== Log opened UTC 2026-11-13 17:43:08",
    "2026-11-13 17:43:09.804 INFO    APP (Main): Command line: \"E:\\Games\\DCS World\\bin-mt\\DCS.exe\" --no-launcher -w DCS",
    "2026-11-13 17:43:09.805 INFO    APP (Main): DCS/2.9.31.29434 (x86_64; MT; Windows NT 10.0.26300)",
    "2026-11-13 17:43:10.000 INFO    EDCORE (Main): something harmless",
    "2026-11-13 17:43:19.558 ERROR   Scripting (Main): [string \"C:\\Users\\Pilot Jane\\Saved Games\\DCS\\Mods/tech/Some Pack/x.lua\"]:268: attempt to index nil",
    "2026-11-13 17:43:20.000 INFO    LOGIN (Main): login as pilot.jane@example.com ok",
    "2026-11-13 17:43:20.100 INFO    Something (Main): token=abc123secret",
    "2026-11-13 17:43:21.000 WARNING EDCORE (Main): C:/Users/Pilot Jane/AppData/Local/Temp/x is slow",
    *[f"2026-11-13 17:44:{i % 60:02d}.000 INFO    VISUALIZER (Main): line {i}" for i in range(400)],
    "2026-11-13 17:44:06.045 INFO    DCSTUNE (Main): simulation started",
    "2026-11-13 17:45:58.617 INFO    DCSTUNE (Main): world objects seen: true nil",
    "2026-11-13 17:45:58.617 INFO    DCSTUNE (Main): position source export: no answer (nil, nil)",
    "2026-11-13 17:45:58.618 INFO    DCSTUNE (Main): result written ok=false reason=benchmark aircraft never appeared",
    "2026-11-13 17:45:59.000 INFO    Dispatcher (Main): Stop\tnow",
])


def test_extract_keeps_the_clues_and_drops_who_the_player_is():
    lines = failurelog.excerpt(LOG, saved_dir=SAVED, dcs_dir=DCS, user="Pilot Jane")
    text = "\n".join(lines)
    assert "Pilot Jane" not in text and "pilot.jane" not in text.lower() and "Users\\" not in text
    assert "abc123secret" not in text and "@" not in text
    assert "<SAVED>\\Mods/tech/Some Pack/x.lua" in text and "<DCS>\\bin-mt\\DCS.exe" in text
    assert "<USER>/AppData" in text
    assert sum("DCSTUNE" in x for x in lines) == 4 and "DCS/2.9.31.29434" in text
    assert "line 399" in text and "line 10 " not in text + " "       # the end of the log, not all of it
    assert all(len(x) <= failurelog.MAX_LINE and "\t" not in x for x in lines)
    assert sum(len(x) + 4 for x in lines) <= failurelog.MAX_BYTES


def test_huge_log_is_capped_but_keeps_the_benchmark_lines():
    big = LOG + "\n" + "\n".join(f"2026-11-13 17:46:00.000 ERROR   X (Main): {'e' * 250} {i}" for i in range(3000))
    lines = failurelog.excerpt(big, saved_dir=SAVED, dcs_dir=DCS, user="Pilot Jane")
    assert len(lines) <= failurelog.MAX_LINES and sum(len(x) + 4 for x in lines) <= failurelog.MAX_BYTES
    assert sum("DCSTUNE" in x for x in lines) == 4 and any("DCS/2.9.31" in x for x in lines)


class _Eng:
    def __init__(self, tmp_path):
        cfg = tmp_path / "DCS" / "Config"
        cfg.mkdir(parents=True)
        (cfg / "dcstune-last-failure.log").write_text(LOG.replace(SAVED, str(tmp_path / "DCS")))
        self.profile = {"path": str(tmp_path / "DCS"), "name": "DCS"}
        self.info = dict(INFO, installs=[{"path": DCS}])

    def optimize(self, full, log, mode="balanced"):
        raise RuntimeError("benchmark did not finish: benchmark aircraft never appeared")


def _fail(app):
    app.start_optimize(False)
    for _ in range(200):
        if app.job["state"] != "running":
            break
        time.sleep(0.01)
    return app.job


def test_failed_test_shows_the_log_and_sends_nothing(tmp_path, monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("the tool must not send anything"))
    app = ui.App(lambda: _Eng(tmp_path))
    job = _fail(app)
    assert job["state"] == "failed" and set(job["failure_log"]) == {"lines"} and job["failure_log"]["lines"]
    with pytest.raises(KeyError):
        app.handle("POST", "/api/failure-log", {})


def test_old_failure_log_is_not_offered(tmp_path, monkeypatch):
    import os
    eng = _Eng(tmp_path)
    old = time.time() - 3600
    os.utime(tmp_path / "DCS" / "Config" / "dcstune-last-failure.log", (old, old))
    app = ui.App(lambda: eng)
    job = _fail(app)
    assert job["state"] == "failed" and "failure_log" not in job
