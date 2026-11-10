"""Byte-preserving reader/writer for DCS ``options.lua``.

DCS writes the file as ``options = { ["section"] = { ["key"] = value, ... }, ... }``
with tab indentation and sorted keys. We never re-serialise the whole file: only the
value text of scalar keys directly inside a top-level section is replaced, so every
other byte (plugins, views, line endings) is left exactly as DCS wrote it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

_SECTION_RE = re.compile(r'^\t\["([^"]+)"\] = \{\s*$')
_ENTRY_RE = re.compile(r'^(\t\t\["([^"]+)"\] = )(.*?)(,?)(\r?\n?)$')
_SECTION_END_RE = re.compile(r'^\t\},?\s*$')

JOURNAL_NAME = "dcstune-journal.json"
BACKUP_PREFIX = "options.lua.dcstune-bak-"


def parse_value(text: str):
    text = text.strip()
    if text == "true":
        return True
    if text == "false":
        return False
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    try:
        return int(text)
    except ValueError:
        return float(text)  # raises ValueError for tables / unknown syntax


def format_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return "%.14g" % value
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    raise TypeError(f"unsupported options.lua value: {value!r}")


class Options:
    def __init__(self, text: str):
        self._lines = text.splitlines(keepends=True)
        self._index: dict[str, dict[str, int]] = {}
        self._bounds: dict[str, tuple[int, int]] = {}
        self._scan()

    # -- loading -----------------------------------------------------------
    @classmethod
    def load(cls, path) -> "Options":
        raw = Path(path).read_bytes()
        return cls(raw.decode("utf-8", errors="surrogateescape"))

    def _scan(self) -> None:
        self._index.clear()
        self._bounds.clear()
        section, start = None, 0
        for i, line in enumerate(self._lines):
            if section is None:
                m = _SECTION_RE.match(line)
                if m:
                    section, start = m.group(1), i
                    self._index[section] = {}
                continue
            if _SECTION_END_RE.match(line):
                self._bounds[section] = (start, i)
                section = None
                continue
            m = _ENTRY_RE.match(line)
            if m and not m.group(3).rstrip().endswith("{"):
                self._index[section][m.group(2)] = i
        if not self._index:
            raise ValueError("not a DCS options.lua (no sections found)")

    # -- reading -----------------------------------------------------------
    def sections(self) -> list[str]:
        return list(self._index)

    def section(self, name: str) -> dict:
        out = {}
        for key, i in self._index.get(name, {}).items():
            try:
                out[key] = parse_value(_ENTRY_RE.match(self._lines[i]).group(3))
            except ValueError:
                pass
        return out

    def get(self, section: str, key: str, default=None):
        i = self._index.get(section, {}).get(key)
        if i is None:
            return default
        try:
            return parse_value(_ENTRY_RE.match(self._lines[i]).group(3))
        except ValueError:
            return default

    # -- writing -----------------------------------------------------------
    def set(self, section: str, key: str, value) -> None:
        if section not in self._bounds:
            raise KeyError(f"section {section!r} not in options.lua")
        text = format_value(value)
        i = self._index[section].get(key)
        if i is not None:
            m = _ENTRY_RE.match(self._lines[i])
            self._lines[i] = f"{m.group(1)}{text}{m.group(4)}{m.group(5)}"
            return
        # New key: insert in DCS's sorted position, copying the file's line ending.
        start, end = self._bounds[section]
        eol = "\r\n" if self._lines[start].endswith("\r\n") else "\n"
        pos = end
        for other, j in sorted(self._index[section].items(), key=lambda kv: kv[1]):
            if other > key:
                pos = j
                break
        self._lines.insert(pos, f'\t\t["{key}"] = {text},{eol}')
        self._scan()

    def update(self, changes: dict) -> None:
        """changes: {"graphics.shadows": 3, "VR.pixel_density": 1.2}"""
        for dotted, value in changes.items():
            section, key = dotted.split(".", 1)
            self.set(section, key, value)

    def dumps(self) -> bytes:
        return "".join(self._lines).encode("utf-8", errors="surrogateescape")

    def save(self, path) -> None:
        atomic_write(Path(path), self.dumps())


# -- file safety -------------------------------------------------------------
def sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".dcstune-tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def backup(options_path) -> Path:
    """Copy options.lua to a timestamped backup beside it; returns the backup path."""
    src = Path(options_path)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = src.with_name(BACKUP_PREFIX + stamp)
    n = 1
    while dst.exists():
        dst = src.with_name(f"{BACKUP_PREFIX}{stamp}-{n}")
        n += 1
    atomic_write(dst, src.read_bytes())
    return dst


def list_backups(options_path) -> list[Path]:
    return sorted(Path(options_path).parent.glob(BACKUP_PREFIX + "*"))


class TrialSession:
    """Guards the player's options.lua while trial settings are written to it.

    ``begin`` stores the original bytes and a journal; ``end`` puts them back. If the
    app or the PC dies in between, ``recover`` (called at every start) restores them.
    """

    def __init__(self, options_path):
        self.path = Path(options_path)
        self.journal = self.path.with_name(JOURNAL_NAME)
        self.saved = self.path.with_name("options.lua.dcstune-original")

    def begin(self) -> None:
        if self.journal.exists():
            recover(self.path)
        original = self.path.read_bytes()
        atomic_write(self.saved, original)
        atomic_write(self.journal, json.dumps({
            "original": self.saved.name,
            "sha256": hashlib.sha256(original).hexdigest(),
            "started": time.time(),
        }).encode())

    def write_trial(self, changes: dict) -> None:
        if not self.journal.exists():
            raise RuntimeError("TrialSession.begin() not called")
        opts = Options(self.saved.read_bytes().decode("utf-8", errors="surrogateescape"))
        opts.update(changes)
        opts.save(self.path)

    def end(self) -> None:
        recover(self.path)

    def __enter__(self):
        self.begin()
        return self

    def __exit__(self, *exc):
        self.end()
        return False


def recover(options_path) -> bool:
    """Restore the original options.lua if a trial session was left open."""
    path = Path(options_path)
    journal = path.with_name(JOURNAL_NAME)
    if not journal.exists():
        return False
    info = json.loads(journal.read_text())
    saved = path.with_name(info["original"])
    if saved.exists():
        data = saved.read_bytes()
        if hashlib.sha256(data).hexdigest() != info["sha256"]:
            raise RuntimeError(f"saved original {saved} does not match journal hash; not restoring")
        atomic_write(path, data)
        saved.unlink()
    journal.unlink()
    return True
