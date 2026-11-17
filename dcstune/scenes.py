# DCS Graphics Optimizer - Fox3 Managed Solutions Inc.
# Created 2026-11-17. The player's choice of map and aircraft for the test (beta issue #23).
"""Which map and aircraft the test flies. The default is free content every player has (Caucasus,
Su-25T). A player can pick another map and aircraft they have installed; the same three scenes are
then flown there. Every offered combination is built ahead of time (mission/generate.py --pack) and
shipped packed; this module only unpacks the one that was picked. Nothing is built on the player's PC."""
from __future__ import annotations

import io
import json
import shutil
import tarfile
import zipfile
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MISSION_SRC = ROOT / "mission" / "dcstune_bench.miz"
PACK = ROOT / "mission" / "scenes.tar.xz"
INDEX = ROOT / "mission" / "scenes.json"
DEFAULT = ("caucasus", "Su-25T")


@lru_cache(maxsize=1)
def index() -> dict:
    """What the pack holds; empty when this copy of the tool has no pack."""
    try:
        data = json.loads(INDEX.read_text())
    except (OSError, ValueError):
        return {"maps": {}, "aircraft": {}, "files": []}
    return data if PACK.exists() else {"maps": {}, "aircraft": {}, "files": []}


def valid(pick) -> tuple[str, str] | None:
    """The pick as (map, aircraft) when the pack has that combination, else None (= the default test)."""
    if not (isinstance(pick, (list, tuple)) and len(pick) == 2 and all(isinstance(x, str) for x in pick)):
        return None
    pick = (pick[0], pick[1])
    entry = index()["maps"].get(pick[0])
    if pick == DEFAULT or not entry or pick[1] not in entry["aircraft"]:
        return None
    return pick


def label(pick) -> str:
    """How the window and the report name a pick: 'F-14B over Syria (Beirut)'."""
    pick = valid(pick) or DEFAULT
    idx = index()
    plane = (idx["aircraft"].get(pick[1]) or {}).get("label") or pick[1]
    where = (idx["maps"].get(pick[0]) or {}).get("label") or "Caucasus (Batumi)"
    return f"{plane} over {where}"


def _has_folder(parent: Path, names: list[str]) -> bool:
    try:
        there = {p.name.lower() for p in parent.iterdir() if p.is_dir()}
    except OSError:
        return False
    return any(n.lower() in there for n in names)


def installed(install_root) -> dict:
    """The maps and aircraft from the pack that this DCS install has, as lists of {key, label}.
    The default map and the free aircraft are always listed."""
    idx, root = index(), Path(install_root) if install_root else None
    maps, planes = [], []
    for key, m in idx["maps"].items():
        if key == DEFAULT[0] or (root and _has_folder(root / "Mods" / "terrains", [m["folder"]])):
            maps.append({"key": key, "label": m["label"]})
    for key, a in idx["aircraft"].items():
        if key == DEFAULT[1] or (root and _has_folder(root / "Mods" / "aircraft", a["folders"])):
            planes.append({"key": key, "label": a["label"]})
    return {"maps": maps, "aircraft": planes}


def write_mission(pick, dst: Path) -> tuple[str, str]:
    """Put the mission for this pick at dst and return the pick that was really used. Anything the
    pack does not hold falls back to the default mission, so a test can always run."""
    pick = valid(pick)
    if pick:
        prefix = f"{pick[0]}/{pick[1]}/"
        files = {}
        with tarfile.open(PACK, "r:xz") as tar:
            for item in tar:
                if item.name.startswith(prefix):
                    files[item.name[len(prefix):]] = tar.extractfile(item).read()
                elif files:
                    break                        # members of one mission sit together
        if set(files) == set(index()["files"]):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for name in index()["files"]:
                    z.writestr(name, files[name])
            Path(dst).write_bytes(buf.getvalue())
            return pick
    shutil.copyfile(MISSION_SRC, dst)
    return DEFAULT
