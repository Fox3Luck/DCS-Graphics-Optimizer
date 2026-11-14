"""Tells the player when a newer version is out (beta feedback: players kept testing old copies
long after the problem they reported was fixed, and the app never told them).

Once per start, in the background, the app asks GitHub for this project's list of releases. The
request carries nothing about the player or the PC: no settings, no hardware, no id, just the
program name and version as the browser-style User-Agent. If GitHub cannot be reached, nothing
is shown and nothing else happens.

DCSTUNE_NO_UPDATE_CHECK=1 switches the check off (used by the automated tests).
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

from . import __version__

REPO = "Fox3Luck/DCS-Graphics-Optimizer"
API_URL = f"https://api.github.com/repos/{REPO}/releases?per_page=20"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
TIMEOUT_SEC = 6
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$")


def parse(version: str) -> tuple | None:
    """'0.1.0-beta.16' -> (0, 1, 0, 0, 16); a full release '0.1.0' sorts after all its betas."""
    m = _VERSION.match((version or "").strip())
    if not m:
        return None
    major, minor, patch, beta = m.groups()
    return (int(major), int(minor), int(patch), 0 if beta else 1, int(beta or 0))


def is_release_page(url: str) -> bool:
    """Only this project's own release pages may be opened from the notice."""
    return isinstance(url, str) and (url == RELEASES_PAGE or url.startswith(RELEASES_PAGE + "/tag/"))


def newest(releases: list, current: str = __version__) -> dict | None:
    """The newest published release that is newer than `current`, as {"version", "url"}."""
    mine = parse(current)
    if mine is None:
        return None
    best = None
    for r in releases if isinstance(releases, list) else []:
        if not isinstance(r, dict) or r.get("draft"):
            continue
        v = parse(str(r.get("tag_name") or ""))
        if v is None or v <= mine or (best and v <= best[0]):
            continue
        url = str(r.get("html_url") or "")
        best = (v, {"version": str(r["tag_name"]).lstrip("v"), "url": url if is_release_page(url) else RELEASES_PAGE})
    return best[1] if best else None


def check(current: str = __version__) -> dict | None:
    """Ask GitHub; None when up to date, switched off, or GitHub cannot be reached."""
    if os.environ.get("DCSTUNE_NO_UPDATE_CHECK") == "1":
        return None
    try:
        req = urllib.request.Request(API_URL, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"DCS-Graphics-Optimizer/{current}"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            return newest(json.loads(resp.read(2_000_000)), current)
    except Exception:
        return None
