"""Opt-in anonymous sharing: the tool's side, the receiving service, and both together."""
import json
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

# The receiving service is kept in a separate repository. These tests run against it when it is
# checked out next to this one (../dcsgo-feedback-server) or DCSGO_FEEDBACK_SERVER points at it;
# without it they are skipped.
import os
sys.path.insert(0, os.environ.get("DCSGO_FEEDBACK_SERVER")
                or str(Path(__file__).resolve().parent.parent.parent / "dcsgo-feedback-server"))
S = pytest.importorskip("feedback_server")

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
    shipped = json.loads((Path(F.__file__).parent / "data" / "feedback.json").read_text())["url"]
    assert shipped == "https://fox3servers.com/dcsgo/v1/feedback"
    assert not F.available()                 # conftest blanks the address for every test
    eng = _engine(tmp_path, monkeypatch)
    assert eng.sharing() == {"available": False, "choice": None}
    for elsewhere in ("http://example.com/x", "https://example.com/x", "http://127.0.0.1:80@example.com/x",
                      "http://127.0.0.1.example.com:80/x", "http://127.0.0.1/x"):      # the override reaches this PC only
        monkeypatch.setenv("DCSTUNE_FEEDBACK_URL", elsewhere)
        assert not F.available()
    monkeypatch.setitem(F._TABLE, "url", "http://fox3.example/x")              # a release address must be https
    assert not F.available()
    monkeypatch.setitem(F._TABLE, "url", "https://fox3.example/x")
    assert F.url() == "https://fox3.example/x"


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


def _post(url, body: bytes, ctype="application/json; charset=utf-8"):
    try:
        req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": ctype})
        with urllib.request.urlopen(req, timeout=5) as r:
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
    assert _post(url, json.dumps(good).encode(), ctype="text/plain") == 415          # what a web page could send
    assert _post(url, json.dumps(dict(good, tool_version="1\n2")).encode()) == 400
    assert _post(url, b"x" * (S.MAX_BYTES + 1)) == 413
    assert _post(url.replace("/v1/feedback", "/other"), b"{}") == 404
    assert len(service()) == 1 and "127.0.0.1" not in json.dumps(service())


def test_service_limits_submissions_per_address(tmp_path, monkeypatch):
    store = S.Store(tmp_path)
    assert all(store.allowed("a", now=1000.0 + i) for i in range(S.PER_HOUR))
    assert not store.allowed("a", now=1100.0) and store.allowed("b", now=1100.0)
    assert store.allowed("a", now=1000.0 + 3601)
    # a flood of other addresses must not reset a blocked sender's count
    store = S.Store(tmp_path)
    monkeypatch.setattr(S, "MAX_ADDRESSES", 50)
    assert all(store.allowed("bad", now=5000.0) for _ in range(S.PER_HOUR)) and not store.allowed("bad", now=5001.0)
    for i in range(49):
        store.allowed(f"other{i}", now=5002.0)
    assert not store.allowed("bad", now=5003.0) and len(store.seen) <= 50


def test_sender_address_comes_only_from_the_proxy_header():
    assert S.sender({"X-Real-IP": " 203.0.113.9 ", "X-Forwarded-For": "1.1.1.1"}, "127.0.0.1", True) == "203.0.113.9"
    assert S.sender({"X-Real-IP": "2001:DB8::1"}, "127.0.0.1", True) == "2001:db8::1"
    for forged in ("1.2.3.4, 5.6.7.8", "x", "", None):
        assert S.sender({"X-Real-IP": forged}, "127.0.0.1", True) == "unknown"
    assert S.sender({"X-Real-IP": "9.9.9.9"}, "127.0.0.1", False) == "127.0.0.1"


def test_service_has_overall_limits(tmp_path, monkeypatch):
    good = F.payload("applied", "0123456789abcdef")
    store = S.Store(tmp_path / "a")
    monkeypatch.setattr(S, "GLOBAL_PER_HOUR", 3)
    for i in range(3):
        store.add(good, now=100.0 + i)
    with pytest.raises(S.Full):
        store.add(good, now=200.0)
    store.add(good, now=100.0 + 3600)                       # an hour later there is room again
    monkeypatch.setattr(S, "GLOBAL_PER_HOUR", 10 ** 6)
    store = S.Store(tmp_path / "b")
    store.add(good)
    monkeypatch.setattr(S, "MAX_FILE_BYTES", 300)
    with pytest.raises(S.Full, match="monthly"):
        [store.add(good) for _ in range(5)]
    monkeypatch.setattr(S, "MAX_FILE_BYTES", 10 ** 9)
    monkeypatch.setattr(S, "MAX_DIR_BYTES", 300)
    with pytest.raises(S.Full, match="folder"):
        [store.add(good) for _ in range(5)]
    f = next((tmp_path / "b").glob("*.jsonl"))
    assert f.stat().st_mode & 0o077 == 0                    # readable by the service account only


def test_service_refuses_odd_shapes_inside_the_audit(tmp_path, monkeypatch, service):
    import os
    url = os.environ["DCSTUNE_FEEDBACK_URL"]
    base = {"schema": "dcsgo-audit/1"}
    deep = cur = {}
    for _ in range(10):
        cur["x"] = {}; cur = cur["x"]
    bad = [dict(base, hardware={"cpu": "x" * 301}), dict(base, hardware={"cpu": "a\x1b[31m"}), dict(base, test=deep),
           dict(base, graphics={"k" * 61: 1}), dict(base, graphics={"a": 10 ** 20}), dict(base, graphics=list(range(4000)))]
    for a in bad:
        assert _post(url, json.dumps(F.payload("result", "0123456789abcdef", a)).encode()) == 400, str(a)[:60]
    assert _post(url, ("[" * 30000).encode()) == 400                       # pathological nesting
    assert _post(url, json.dumps(dict(F.payload("feedback", "0123456789abcdef"), comment="a\x07b")).encode()) == 400
    assert _post(url, json.dumps(F.payload("feedback", "0123456789abcdef", comment="two\nlines")).encode()) == 204
    assert len(service()) == 1


def test_service_tells_the_tool_when_it_is_full(tmp_path, monkeypatch, service):
    import os
    monkeypatch.setattr(S, "GLOBAL_PER_HOUR", 0)
    assert _post(os.environ["DCSTUNE_FEEDBACK_URL"], json.dumps(F.payload("applied", "0123456789abcdef")).encode()) == 503


def test_tool_does_not_follow_redirects(tmp_path, monkeypatch, service):
    import http.server
    hits = []

    class Redirect(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_POST(self):
            hits.append(self.path)
            self.send_response(307); self.send_header("Location", os.environ["REAL"]); self.end_headers()
    import os
    monkeypatch.setenv("REAL", os.environ["DCSTUNE_FEEDBACK_URL"])
    srv = http.server.HTTPServer(("127.0.0.1", 0), Redirect)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("DCSTUNE_FEEDBACK_URL", f"http://127.0.0.1:{srv.server_address[1]}/v1/feedback")
    assert F.send(F.payload("applied", "0123456789abcdef")) is False
    srv.shutdown()
    assert hits == ["/v1/feedback"] and service() == []
