"""The tool sends nothing about the player; it only opens the project's GitHub issues or Discord
channel in the player's browser when they press a button."""
import re
import webbrowser
from pathlib import Path

import pytest

import dcstune
from dcstune import community, ui

SRC = Path(dcstune.__file__).parent


def test_only_the_two_known_pages_can_be_opened(monkeypatch):
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url) or True)
    app = ui.App(lambda: None)
    assert "GitHub" in app.handle("POST", "/api/open-link", {"which": "issues"})["message"]
    assert "Discord" in app.handle("POST", "/api/open-link", {"which": "discord"})["message"]
    assert opened == ["https://github.com/Fox3Luck/DCS-Graphics-Optimizer/issues",
                      "https://discord.com/channels/814940459134484511/1571736773682274427"]
    for bad in ("https://example.com", "", None, "releases"):
        with pytest.raises(RuntimeError):
            app.handle("POST", "/api/open-link", {"which": bad})
    assert len(opened) == 2


def test_result_sharing_is_gone():
    app = ui.App(lambda: None)
    for path in ("/api/sharing", "/api/feedback", "/api/failure-log"):
        with pytest.raises(KeyError):
            app.handle("POST", path, {})
    assert not (SRC / "feedback.py").exists() and not (SRC / "data" / "feedback.json").exists()
    # the only address the program itself talks to is GitHub's release list (updates.py)
    for f in SRC.glob("*.py"):
        if f.name != "updates.py":
            assert "urllib.request" not in f.read_text(), f.name
    page = (SRC / "ui.html").read_text()
    assert not re.search(r"anonymous result|share-yes|fb-send|/api/sharing|/api/feedback", page)
    assert 'data-link="issues"' in page and 'data-link="discord"' in page
