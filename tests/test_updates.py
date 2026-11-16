"""The "newer version available" notice (players kept testing old copies)."""
import json

from dcstune import updates
from dcstune.ui import App

PAGE = updates.RELEASES_PAGE


def rel(tag, draft=False, url=None):
    return {"tag_name": tag, "draft": draft, "html_url": url or f"{PAGE}/tag/{tag}"}


def test_version_order():
    assert updates.parse("0.1.0-beta.9") < updates.parse("0.1.0-beta.10") < updates.parse("v0.1.0-beta.17")
    assert updates.parse("0.1.0-beta.40") < updates.parse("0.1.0") < updates.parse("0.1.1-beta.1")
    assert updates.parse("nightly") is None


def test_newest_newer_release_is_offered():
    found = updates.newest([rel("v0.1.0-beta.15"), rel("v0.1.0-beta.17"), rel("v0.1.0-beta.16")], "0.1.0-beta.16")
    assert found == {"version": "0.1.0-beta.17", "url": f"{PAGE}/tag/v0.1.0-beta.17"}


def test_nothing_when_up_to_date_or_only_drafts():
    assert updates.newest([rel("v0.1.0-beta.16"), rel("v0.1.0-beta.12")], "0.1.0-beta.16") is None
    assert updates.newest([rel("v0.1.0-beta.18", draft=True)], "0.1.0-beta.16") is None
    assert updates.newest({"message": "rate limited"}, "0.1.0-beta.16") is None


def test_foreign_link_is_replaced_by_the_releases_page():
    found = updates.newest([rel("v0.1.0-beta.17", url="https://example.com/evil.exe")], "0.1.0-beta.16")
    assert found["url"] == PAGE
    assert not updates.is_release_page("https://github.com/Fox3Luck/DCS-Graphics-Optimizer/releasesX")
    assert not updates.is_release_page("https://github.com/someone/else/releases")


def test_check_is_off_in_tests_and_silent_without_network(monkeypatch):
    assert updates.check() is None                       # DCSTUNE_NO_UPDATE_CHECK=1 from conftest
    monkeypatch.delenv("DCSTUNE_NO_UPDATE_CHECK")
    def boom(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr(updates.urllib.request, "urlopen", boom)
    assert updates.check() is None


def test_check_reads_github_answer(monkeypatch):
    monkeypatch.delenv("DCSTUNE_NO_UPDATE_CHECK")
    seen = {}
    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n): return json.dumps([rel("v0.1.0-beta.99")]).encode()
    def fake(req, timeout):
        seen["url"], seen["ua"] = req.full_url, req.get_header("User-agent")
        return Resp()
    monkeypatch.setattr(updates.urllib.request, "urlopen", fake)
    assert updates.check("0.1.0-beta.16")["version"] == "0.1.0-beta.99"
    assert seen["url"] == updates.API_URL and seen["ua"] == "DCS-Graphics-Optimizer/0.1.0-beta.16"


def test_window_routes(monkeypatch):
    opened = []
    monkeypatch.setattr("dcstune.ui.webbrowser.open", opened.append)
    app = App(engine_factory=lambda: None)
    v = app.handle("GET", "/api/version", {})
    assert v["update"] is None and v["version"]
    app.update = {"version": "0.1.0-beta.99", "url": f"{PAGE}/tag/v0.1.0-beta.99"}
    app.handle("POST", "/api/open-download", {})
    app.update = {"version": "0.1.0-beta.99", "url": "https://example.com/x"}
    try:
        app.handle("POST", "/api/open-download", {})
        raise AssertionError("opened a foreign page")
    except RuntimeError:
        pass
    assert opened == [f"{PAGE}/tag/v0.1.0-beta.99"]


def test_vr_test_build_is_only_offered_newer_vr_test_builds(monkeypatch, tmp_path):
    # Issue #42: the notice in VR test build 2 sent VR volunteers to a regular beta, which tests on
    # the monitor.
    from dcstune import vr
    rels = [rel("v0.1.0-beta.22"), rel("vr-test-2"), rel("vr-test-3"), rel("vr-test-1"), rel("vr-test-4", draft=True)]
    assert updates.newest_vr_test(rels, 2)["version"] == "VR test build 3"
    assert updates.newest_vr_test(rels, 2)["url"].endswith("/tag/vr-test-3")
    assert updates.newest_vr_test(rels, 3) is None
    assert updates.newest_vr_test([rel("v0.1.0-beta.22")], 2) is None
    marker = tmp_path / "vr_test_build"
    monkeypatch.setattr(vr, "TEST_BUILD_MARKER", marker)
    assert vr.test_build_number() == 0
    marker.write_text("3\n")
    assert vr.test_build() and vr.test_build_number() == 3
    marker.write_text("VR test build: in-headset testing is switched on.")      # builds before the number
    assert vr.test_build_number() == 0
