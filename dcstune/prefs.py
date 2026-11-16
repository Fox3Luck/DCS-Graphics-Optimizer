# DCS Graphics Optimizer - Fox3 Managed Solutions Inc.
# Created 2026-11-16. Keeps the player's own choices (such as the headset picked) in the DCS profile.
"""The player's answers kept in a DCS profile (for now: which headset they picked).
Stored as Config\\dcstune-prefs.json in that profile; never sent anywhere."""
from __future__ import annotations

import json
from pathlib import Path


def _file(profile: dict) -> Path:
    return Path(profile["path"]) / "Config" / "dcstune-prefs.json"


def _load(profile: dict) -> dict:
    try:
        prefs = json.loads(_file(profile).read_text())
    except (OSError, ValueError):
        return {}
    return prefs if isinstance(prefs, dict) else {}


def get_pref(profile: dict, key: str):
    """One saved answer, or None."""
    return _load(profile).get(key)


def set_pref(profile: dict, key: str, value) -> None:
    from .optionslua import atomic_write
    prefs = _load(profile)
    prefs[key] = value
    atomic_write(_file(profile), json.dumps(prefs).encode())
