# DCS Graphics Optimizer - Fox3 Managed Solutions Inc.
# Created 2026-11-11. Shared test setup: no update check and no browser during tests.
import pytest


@pytest.fixture(autouse=True)
def _no_update_check(monkeypatch):
    """Tests never ask GitHub for releases."""
    monkeypatch.setenv("DCSTUNE_NO_UPDATE_CHECK", "1")


@pytest.fixture(autouse=True)
def _no_browser(monkeypatch):
    """Tests never open a page in a real browser."""
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: True)
