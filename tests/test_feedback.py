"""Opt-in anonymous sharing: the tool's side, the receiving service, and both together."""
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
import feedback_server as S

from dcstune import feedback as F
from test_vr import _FakeBench, _engine          # noqa: F401  (engine with a fake DCS)


@pytest.fixture
def service(tmp_path, monkeypatch):
    store = S.Store(tmp_path / "received")
    srv = S.make_server(store)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("DCSTUNE_FEEDBACK_URL", f"http://127.0.0.1:{srv.server_address[1]}/v1/feedback")
    monkeypatch.delenv("DCSTUNE_VR_BENCH", raising=False)

    def received():
        return [json.loads(l) for f in sorted((tmp_path / "received").glob("*.jsonl")) for l in f.read_text().splitlines()]
    yield received
    srv.shutdown()


def _wait(received, n):
    import time
    for _ in range(100):
        if len(received()) >= n:
            break
        time.sleep(0.02)
    return received()


def test_feature_is_absent_without_an_address(tmp_path, monkeypatch):
    monkeypatch.delenv("DCSTUNE_FEEDBACK_URL", raising=False)
    assert json.loads((Path(F.__file__).parent / "data" / "feedback.json").read_text())["url"] == ""   # as shipped
    assert not F.available()
    eng = _engine(tmp_path, monkeypatch)
    assert eng.sharing() == {"available": False, "choice": None}
    monkeypatch.setenv("DCSTUNE_FEEDBACK_URL", "http://example.com/x")       # only https (or this PC, for tests)
    assert not F.available()


def test_nothing_is_sent_until_the_player_says_yes(tmp_path, monkeypatch, service):
    eng = _engine(tmp_path, monkeypatch)
    assert eng.sharing() == {"available": True, "choice": None}
    eng.optimize(False, lambda *_: None)
    eng.set_sharing(False)
    assert eng.sharing()["choice"] is False
    eng.optimize(False, lambda *_: None)
    with pytest.raises(RuntimeError, match="switched off"):
        eng.feedback("better", "hello")
    assert service() == []


def test_opted_in_result_follow_ups_and_comment_arrive_anonymously(tmp_path, monkeypatch, service):
    from dcstune import bench
    monkeypatch.setattr(bench, "dcs_running", lambda: False)
    eng = _engine(tmp_path, monkeypatch, **{"VR.pixel_density": 1.3})
    eng.set_sharing(True)
    log = []
    rep = eng.optimize(False, log.append)
    assert any("Sent the anonymous result" in l for l in log)
    got = service()
    assert len(got) == 1 and got[0]["event"] == "result" and got[0]["id"] == rep["id"] and len(rep["id"]) == 16
    audit = got[0]["audit"]
    assert audit["hardware"]["cpu"] and audit["vr"]["detected"]["headset"] == "Pimax Crystal Light"
    # what was sent is what the report folder's audit.json says
    saved = json.loads((tmp_path / "DCS Graphics Optimizer Reports" / rep["dir"] / "audit.json").read_text())
    assert {k: v for k, v in saved.items() if k != "created"} == {k: v for k, v in audit.items() if k != "created"}
    text = json.dumps(got)
    assert str(tmp_path) not in text and "Users" not in text and set(got[0]) == {"received", "schema", "tool_version", "event", "id", "audit"}
    if rep.get("changes"):
        eng.apply()
        eng.undo()
        got = _wait(service, 3)
        assert sorted(g["event"] for g in got[1:]) == ["applied", "undone"] and all(g["id"] == rep["id"] for g in got)
    n = len(service())
    assert "Thank you" in eng.feedback("worse", "  shimmer on the horizon  ")
    last = service()[-1]
    assert len(service()) == n + 1 and last["event"] == "feedback" and last["feel"] == "worse" and last["comment"] == "shimmer on the horizon"
    assert eng._report()["feedback"] == {"feel": "worse", "comment": "shimmer on the horizon"}
    with pytest.raises(RuntimeError, match="Choose better"):
        eng.feedback(None, "   ")


def test_a_dead_service_never_gets_in_the_way(tmp_path, monkeypatch):
    monkeypatch.setenv("DCSTUNE_FEEDBACK_URL", "http://127.0.0.1:9/v1/feedback")
    monkeypatch.delenv("DCSTUNE_VR_BENCH", raising=False)
    eng = _engine(tmp_path, monkeypatch)
    eng.set_sharing(True)
    log = []
    rep = eng.optimize(False, log.append)
    assert rep["before"] and any("could not be sent" in l for l in log)


def test_window_asks_before_the_first_test(tmp_path, monkeypatch, service):
    from dcstune import ui
    eng = _engine(tmp_path, monkeypatch)
    app = ui.App(lambda: eng)
    with pytest.raises(RuntimeError, match="answer the question"):
        app.handle("POST", "/api/optimize", {"full": False})
    assert "Nothing will be sent" in app.handle("POST", "/api/sharing", {"share": "yes"})["message"]   # only a real yes counts
    assert app.handle("POST", "/api/sharing", {"share": True})["message"].startswith("Thank you")
    assert app.handle("GET", "/api/scorecard", {})["sharing"] == {"available": True, "choice": True}
    page = (Path(ui.__file__).parent / "ui.html").read_text()
    for must in ("anonymous", "What is sent", "What is not sent", "What it is for", "audit.json", "change your answer"):
        assert must in page


def _post(url, body: bytes):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST"), timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_service_refuses_everything_else(tmp_path, monkeypatch, service):
    import os
    url = os.environ["DCSTUNE_FEEDBACK_URL"]
    good = F.payload("applied", "0123456789abcdef")
    assert _post(url, json.dumps(good).encode()) == 204
    bad = [dict(good, id="../../etc"), dict(good, event="delete"), dict(good, extra=1), dict(good, schema="x"),
           dict(good, comment="x" * 1001), dict(good, feel="angry"), dict(good, audit={"schema": "dcsgo-audit/1"}),
           dict(good, event="result"), dict(good, event="result", audit={"schema": "dcsgo-audit/1", "ip": "1.2.3.4"}), [1]]
    for b in bad:
        assert _post(url, json.dumps(b).encode()) == 400, b
    assert _post(url, b"not json") == 400
    assert _post(url, b"x" * (S.MAX_BYTES + 1)) == 413
    assert _post(url.replace("/v1/feedback", "/other"), b"{}") == 404
    assert len(service()) == 1 and "127.0.0.1" not in json.dumps(service())


def test_service_limits_submissions_per_address(tmp_path):
    store = S.Store(tmp_path)
    assert all(store.allowed("a", now=1000.0 + i) for i in range(S.PER_HOUR))
    assert not store.allowed("a", now=1100.0) and store.allowed("b", now=1100.0)
    assert store.allowed("a", now=1000.0 + 3601)
