"""A short, anonymized extract of DCS's log for a failed test (beta feedback: logs were the only
way to see why "benchmark aircraft never appeared", and asking each player for a file is slow).

The extract keeps what explains a failure - every line the benchmark script wrote (DCSTUNE),
DCS's errors and warnings, and the end of the log - and removes what could identify the player:
the Windows user name and folder paths become <USER>, <SAVED> and <DCS>, and lines that mention
logins, passwords, tokens, serials or e-mail addresses are left out. Mod and module names stay,
because they are the likely cause. Nothing is sent from here: see feedback.py and ui.py for when
it is (automatically only when the player agreed to share results, otherwise only on a click).
"""
from __future__ import annotations

import getpass
import os
import re
from pathlib import Path

TAIL_LINES = 150
MAX_LINES = 600
MAX_LINE = 280          # the receiver refuses longer texts
MAX_BYTES = 40_000      # leaves room in the receiver's 64 KB per submission
_DROP = re.compile(r"login|password|passwd|token|serial|@|e-?mail|steamid|user ?id", re.I)
_USERS_DIR = re.compile(r"([A-Za-z]:[\\/]+Users[\\/]+)[^\\/\s\"']+", re.I)
_CONTROL = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")


def _variants(path: str) -> list[str]:
    p = path.rstrip("\\/")
    return sorted({p, p.replace("\\", "/"), p.replace("/", "\\")}, key=len, reverse=True) if p else []


def redact(line: str, saved_dir: str = "", dcs_dir: str = "", user: str | None = None) -> str | None:
    """One log line made anonymous, or None when it should not be sent at all."""
    if _DROP.search(line):
        return None
    out = line.replace("\t", " ")
    for path, mark in ((saved_dir, "<SAVED>"), (dcs_dir, "<DCS>")):
        for v in _variants(path):
            out = re.sub(re.escape(v), mark, out, flags=re.I)
    user = user if user is not None else _user()
    if user and len(user) >= 3:            # first: a user name with a space would defeat the pattern below
        out = re.sub(re.escape(user), "<USER>", out, flags=re.I)
    out = _USERS_DIR.sub(r"<USER>", out)
    out = _CONTROL.sub(" ", out).rstrip()
    return out[:MAX_LINE]


def _user() -> str:
    try:
        return os.environ.get("USERNAME") or getpass.getuser() or ""
    except Exception:
        return ""


def excerpt(text: str, saved_dir: str = "", dcs_dir: str = "", user: str | None = None) -> list[str]:
    """The lines worth sending, in log order, anonymized and size-limited."""
    lines = text.splitlines()
    keep = set(range(max(0, len(lines) - TAIL_LINES), len(lines)))
    keep.update(i for i, ln in enumerate(lines)
                if "DCSTUNE" in ln or " ERROR " in ln or " WARNING " in ln or ln.startswith("=== Log"))
    first_lines = [i for i, ln in enumerate(lines[:12]) if "APP (Main)" in ln]      # DCS version, command line
    keep.update(first_lines)
    out, size, last = [], 0, None
    for i in sorted(keep):
        r = redact(lines[i], saved_dir, dcs_dir, user)
        if not r or r == last:
            continue
        out.append(r)
        last = r
    # Too long: keep every DCSTUNE line and the DCS version/command line, then the newest of the rest.
    def protected(x):
        return "DCSTUNE" in x or "APP (Main)" in x or x.startswith("=== Log")
    while (len(out) > MAX_LINES or sum(len(x) + 4 for x in out) > MAX_BYTES):
        drop = next((k for k, x in enumerate(out) if not protected(x)), None)
        if drop is None:
            out = out[-MAX_LINES:]
            break
        del out[drop]
    return out


def for_profile(profile: dict, install: dict | None, since: float = 0.0) -> list[str] | None:
    """The extract of this profile's kept failure log, or None if there is none from this test
    (written before `since`, a time.time() value)."""
    p = Path(profile["path"]) / "Config" / "dcstune-last-failure.log"
    try:
        if p.stat().st_mtime < since:
            return None
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return excerpt(text, saved_dir=profile["path"], dcs_dir=(install or {}).get("path", ""))
