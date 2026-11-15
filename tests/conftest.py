import pytest


@pytest.fixture(autouse=True)
def _never_send_to_the_real_receiver(monkeypatch):
    """The release has the live address built in. Tests must never post to it: by default the
    feature is absent, and tests that exercise sending point it at a receiver on this machine."""
    from dcstune import feedback
    monkeypatch.setitem(feedback._TABLE, "url", "")
    monkeypatch.delenv("DCSTUNE_FEEDBACK_URL", raising=False)


@pytest.fixture(autouse=True)
def _no_update_check(monkeypatch):
    """Tests never ask GitHub for releases."""
    monkeypatch.setenv("DCSTUNE_NO_UPDATE_CHECK", "1")


@pytest.fixture(autouse=True)
def _english_unless_a_test_asks(monkeypatch, tmp_path):
    """Tests read English whatever language this PC's Windows is in, and never touch the
    player's saved language choice."""
    from dcstune import i18n
    monkeypatch.setenv("DCSTUNE_LANG", "en")
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(i18n, "_current", None)
