"""Anonymous result sharing (opt-in). Off unless the player says yes when the tool asks.

What is sent is the audit file of a test (see audit.py: hardware, DCS and VR set-up, settings,
results - no names, folder paths or account details), whether the recommendation was applied or
undone, and anything the player chooses to add. Each test gets a random id so those follow-ups
can be matched to it; there is no id for the PC or the player.

The address results go to is in data/feedback.json. While it is empty the whole feature is
absent: the tool does not ask and sends nothing."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

SCHEMA = "dcsgo-feedback/1"
FEELS = ("better", "same", "worse")
COMMENT_MAX = 1000
TIMEOUT_SEC = 8
_TABLE = json.loads((Path(__file__).parent / "data" / "feedback.json").read_text())


def url() -> str:
    """The address built into this release (https only). For development and the automated
    tests, DCSTUNE_FEEDBACK_URL may point at a receiver on this PC - and nowhere else."""
    dev = (os.environ.get("DCSTUNE_FEEDBACK_URL") or "").strip()
    if dev:
        try:
            u = urllib.parse.urlsplit(dev)
            if u.scheme == "http" and u.hostname == "127.0.0.1" and u.port and not u.username and "@" not in u.netloc:
                return dev
        except ValueError:
            pass
    u = (_TABLE.get("url") or "").strip()
    return u if u.startswith("https://") else ""


def available() -> bool:
    return bool(url())


def _prefs(profile: dict) -> Path:
    return Path(profile["path"]) / "Config" / "dcstune-prefs.json"


def choice(profile: dict):
    """True / False as the player answered, None if they have not been asked yet."""
    try:
        v = json.loads(_prefs(profile).read_text()).get("share")
    except (OSError, ValueError, AttributeError):
        return None
    return v if isinstance(v, bool) else None


def set_choice(profile: dict, share: bool) -> None:
    from .optionslua import atomic_write
    atomic_write(_prefs(profile), json.dumps({"share": bool(share)}).encode())


def on(profile: dict) -> bool:
    return available() and choice(profile) is True


def payload(event: str, report_id: str, audit: dict | None = None, feel: str | None = None,
            comment: str | None = None) -> dict:
    from . import __version__
    p = {"schema": SCHEMA, "tool_version": __version__, "event": event, "id": report_id}
    if audit is not None:
        p["audit"] = audit
    if feel in FEELS:
        p["feel"] = feel
    if comment and comment.strip():
        p["comment"] = comment.strip()[:COMMENT_MAX]
    return p


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):      # the result goes to the built-in address or nowhere
        return None


def send(p: dict) -> bool:
    """One attempt, short timeout, never raises: sharing must not get in the player's way."""
    try:
        req = urllib.request.Request(url(), data=json.dumps(p, default=str).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "DCSGraphicsOptimizer"})
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=TIMEOUT_SEC) as r:
            return 200 <= r.status < 300
    except Exception:
        return False
