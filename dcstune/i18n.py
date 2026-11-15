"""Languages for the window and the saved report. English is the source language; every other
language is a table from the English sentence to its translation (lang_tr.py is Turkish).

The rest of the program keeps writing plain English. Text is translated where it leaves the
program: the answers the window receives (ui.py), the progress log, error messages and the report
page (report.py). That keeps the measuring and rating code free of language concerns, lets a
report saved in one language be read in another, and means a sentence that has no translation
yet is simply shown in English.

A table key is the English sentence. Parts that vary are written {0}, {1}, ... (any text) or
{n0}, {n1}, ... (a number); the translation uses the same names and may put them in any order.
Text captured by {0} is itself translated when the table has it ("measured", "High", ...).
Keys starting with "ui." are fixed texts of the page (see data-t in ui.html).

  DCSTUNE_LANG=en|tr   forces a language (used by the automated tests)
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

DEFAULT = "en"
NAMES = {"en": "English", "tr": "Türkçe"}       # what the language switch shows
_PLACEHOLDER = re.compile(r"(\{n?\d\})")
_NUMBER = r"-?\d+(?:[.,]\d+)?"
_current: str | None = None


def _table(code: str) -> dict:
    if code == "tr":
        from .lang_tr import TR
        return TR
    return {}


def _file() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "DCS Graphics Optimizer" / "language.json"


def lang() -> str:
    """The language in use: forced by DCSTUNE_LANG, else the language the player picked, else
    English. The tool starts in English until the player chooses otherwise."""
    global _current
    forced = (os.environ.get("DCSTUNE_LANG") or "").strip().lower()
    if forced in NAMES:
        return forced
    if _current is None:
        try:
            saved = json.loads(_file().read_text(encoding="utf-8")).get("lang")
        except (OSError, ValueError, AttributeError):
            saved = None
        _current = saved if saved in NAMES else DEFAULT
    return _current


def set_lang(code: str) -> str:
    """Remember the player's choice. Returns the language now in use."""
    global _current
    if code not in NAMES:
        raise ValueError(code)
    _current = code
    try:
        f = _file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"lang": code}), encoding="utf-8")
    except OSError:
        pass                       # the choice still holds until the window is closed
    return lang()


@lru_cache(maxsize=None)
def _patterns(code: str) -> list:
    """(compiled English pattern, placeholder names, translation), most specific first."""
    out = []
    for key, value in _table(code).items():
        if key.startswith("ui.") or "{" not in key:
            continue
        parts = _PLACEHOLDER.split(key)
        names = [p[1:-1] for p in parts[1::2]]
        if not names:
            continue
        rx = "".join((f"({_NUMBER})" if p[1] == "n" else "(.+?)") if i % 2 else re.escape(p)
                     for i, p in enumerate(parts))
        out.append((sum(len(p) for p in parts[0::2]), re.compile(rx, re.S), names, value))
    out.sort(key=lambda t: -t[0])
    return [t[1:] for t in out]


@lru_cache(maxsize=4096)
def _translate(text: str, code: str, depth: int) -> str:
    table = _table(code)
    if text in table:
        return table[text]
    lead = text[:len(text) - len(text.lstrip())]          # log lines are indented
    core = text.strip()
    if not core:
        return text
    tail = text[len(lead) + len(core):]
    hit = table.get(core)
    if hit is not None:
        return lead + hit + tail
    if depth < 4:
        for rx, names, value in _patterns(code):
            m = rx.fullmatch(core)
            if m:
                for name, got in zip(names, m.groups()):
                    value = value.replace("{" + name + "}",
                                          got if name[0] == "n" else _translate(got, code, depth + 1))
                return lead + value + tail
        if ", " in core:                                   # a list: "Shadows = High, Water = Low"
            parts = [_translate(p, code, depth + 1) for p in core.split(", ")]
            if parts != core.split(", "):
                return lead + ", ".join(parts) + tail
    return text


def tr(text, code: str | None = None):
    """The text in the current language; unchanged when it is English or has no translation."""
    code = code or lang()
    if code == DEFAULT or not isinstance(text, str) or not text:
        return text
    return _translate(text, code, 0)


# Parts of an answer that are data, not sentences: left exactly as they are.
_SKIP = {"report", "report_html", "failure_log", "profiles", "profile_path", "install_path", "profile", "profile_dir",
         "state", "severity", "grade", "what", "version", "url", "lang", "languages", "telemetry", "bench"}


def tr_deep(obj, code: str | None = None):
    """A copy of a JSON-like answer with every sentence in it translated."""
    code = code or lang()
    if code == DEFAULT:
        return obj
    if isinstance(obj, str):
        return tr(obj, code)
    if isinstance(obj, list):
        return [tr_deep(x, code) for x in obj]
    if isinstance(obj, dict):
        return {k: (v if k in _SKIP else tr_deep(v, code)) for k, v in obj.items()}
    return obj


def page_strings(code: str | None = None) -> str:
    """The current language's table as JSON for the page's own script (empty for English)."""
    text = json.dumps(_table(code or lang()), ensure_ascii=False)
    return text.replace("</", "<\\/").replace("<!--", "<\\!--")
