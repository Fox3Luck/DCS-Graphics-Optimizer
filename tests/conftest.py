import pytest


@pytest.fixture(autouse=True)
def _never_send_to_the_real_receiver(monkeypatch):
    """The release has the live address built in. Tests must never post to it: by default the
    feature is absent, and tests that exercise sending point it at a receiver on this machine."""
    from dcstune import feedback
    monkeypatch.setitem(feedback._TABLE, "url", "")
    monkeypatch.delenv("DCSTUNE_FEEDBACK_URL", raising=False)
