"""VR: what headset is in use, what the frame-rate goal is, and what VR-specific advice
applies. Everything here works without the headset being connected.

Measuring in VR (starting DCS in the headset) is experimental until it has been proven on
real headsets; it is switched on with the environment variable DCSTUNE_VR_BENCH=1.
Where each fact comes from is recorded in docs/VR-SOURCES.md.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

TABLE = json.loads((Path(__file__).parent / "data" / "vr.json").read_text())
FIXED = TABLE["fixed"]

# Rough conversion from "pixels the headset asks for" to "pixels a monitor would cost",
# anchored on Pimax's published DCS figures (RTX 3080 and RTX 4090 on a Crystal Light).
# It only feeds the no-test estimate, which is labeled as rough; a real test replaces it.
PIXEL_FACTOR = 0.4
CPU_FACTOR = 1.2        # two views to prepare instead of one
QUAD_FACTOR = 0.65      # quad views: Pimax measured GPU load 92% -> 61% on an RTX 4090


def bench_enabled() -> bool:
    return os.environ.get("DCSTUNE_VR_BENCH") == "1"


def runtime_name(path: str | None) -> str | None:
    if not path:
        return None
    for pattern, name in TABLE["runtimes"]:
        if re.search(pattern, path, re.I):
            return name
    return Path(path.replace("\\", "/")).stem


def detect(raw: dict | None) -> dict:
    """raw: what sysinfo read - {"runtime": path of the active OpenXR runtime,
    "layers": [OpenXR API layer names], "pimax_profile": text of Pimax's profile.json}."""
    raw = raw or {}
    layers = [str(x) for x in (raw.get("layers") or [])]
    out = {"runtime": runtime_name(raw.get("runtime")), "headset": None, "render_quality": None,
           "layers": layers, "quad_layer": any(re.search("quad", x, re.I) for x in layers)}
    try:
        profile = json.loads(raw.get("pimax_profile") or "")
    except ValueError:
        profile = None
    if out["runtime"] == "Pimax" and isinstance(profile, dict):
        for key in profile:
            code = key[len("Pimax "):] if key.startswith("Pimax ") else None
            if code in TABLE["pimax_models"]:
                out["headset"] = TABLE["pimax_models"][code]
        rq = profile.get("pixels_per_display_pixel_rate")
        if isinstance(rq, (int, float)) and 0.2 <= rq <= 3:
            out["render_quality"] = round(float(rq), 2)
        out["vendor_foveation"] = bool(profile.get("enable_foveated_rendering"))
    return out


def state(info: dict, options: dict) -> dict | None:
    """None when VR is switched off in this DCS profile."""
    if not options.get("VR.enable"):
        return None
    found = detect(info.get("vr"))
    spec = next((h for h in TABLE["headsets"] if h["name"] == found["headset"]), None)
    known = spec is not None
    spec = dict(spec or TABLE["unknown_headset"])
    refresh = sorted(spec["refresh"])
    target = 90 if 90 in refresh else refresh[-1]
    pd = options.get("VR.pixel_density")
    pd = float(pd) if isinstance(pd, (int, float)) and not isinstance(pd, bool) else 1.0
    hires = known and spec["eye_w"] >= TABLE["hires_eye_w"]
    return {"runtime": found["runtime"], "headset": found["headset"], "known": known,
            "eye_w": spec["eye_w"], "eye_h": spec["eye_h"], "refresh": refresh,
            "eye_tracking": spec["eye_tracking"], "hires": hires,
            "render_quality": found["render_quality"], "pixel_density": pd,
            "quad_view": bool(options.get("VR.openxr_quadView")),
            "quad_layer": found["quad_layer"], "vendor_foveation": found.get("vendor_foveation", False),
            "target": target, "steps": goal_steps(refresh, target),
            "model": {"eye_px": spec["eye_w"] * spec["eye_h"],
                      "render_quality": found["render_quality"] or 1.0, "pd": pd,
                      "quad": bool(options.get("VR.openxr_quadView"))}}


def goal_steps(refresh: list[int], target: int) -> list[int]:
    """Frame-rate goals to fall back through: each refresh rate the headset offers at or
    below the goal, then half the lowest one (what motion smoothing locks to)."""
    steps = [r for r in sorted(refresh, reverse=True) if r <= target] or [target]
    return steps + [round(steps[-1] / 2)]


def describe(st: dict) -> str:
    # Pimax Play records the model once a headset has connected; until then only the brand is known.
    name = st["headset"] or ("Pimax headset (model not known yet)" if st.get("runtime") == "Pimax" else "Headset not recognized")
    return name + (f" ({st['eye_w']} x {st['eye_h']} per eye)" if st["known"] else "")


def fixed_changes(st: dict, options: dict) -> dict:
    """DCS-side changes that every source agrees on for VR. Only ones that differ from the
    player's settings are returned. Quad views itself is never switched: it needs matching
    support in the headset software, and DCS fails to start VR without it."""
    out = {}
    for f in FIXED:
        when = f["when"]
        if (when == "hires" and not st["hires"]) or (when == "quad" and not st["quad_view"]):
            continue
        cur = options.get(f["key"])
        if cur is None or cur == f["to"]:
            continue
        if f["key"] == "VR.pixel_density" and not cur > f["to"]:
            continue                      # below 1.0 is the player trading sharpness for speed
        out[f["key"]] = f["to"]
    return out


def fixed_row(key: str, old, new) -> dict | None:
    """A change-list row for one of the fixed VR changes."""
    f = next((x for x in FIXED if x["key"] == key), None)
    if not f:
        return None

    def name(v):
        if "fmt" in f and isinstance(v, (int, float)) and not isinstance(v, bool):
            return f["fmt"].format(v)
        return f.get("names", {}).get(str(v).lower() if isinstance(v, bool) else str(v), str(v))
    return {"key": key, "label": f["label"], "from": name(old), "to": name(new),
            "direction": "down", "why": f["why"]}


def rules(st: dict, o: dict, machine: dict, ratio: float):
    """Findings as (severity, penalty, text[, "untouched"]). "untouched" marks things this
    tool does not change itself (they live in the headset's own software)."""
    soft = "Pimax Play" if st["runtime"] == "Pimax" else "your headset software"
    if not st["known"]:
        yield ("info", 0, "VR is on, but this headset is not in our table yet"
               + (f" (runtime: {st['runtime']})" if st["runtime"] else "")
               + ". The estimate assumes a typical headset.", "untouched")
    if st["hires"] and st["pixel_density"] > 1.0:
        yield ("warn", 6, f"VR pixel density is {st['pixel_density']:.2f}. On a {st['headset']} 1.0 is already "
                          "sharper than the lenses can show; the extra pixels only cost frame rate.")
    if st["pixel_density"] > 1.0 and (st["render_quality"] or 1.0) > 1.0:
        yield ("warn", 4, f"Both DCS pixel density and {soft} render quality are above 1.0. "
                          "They multiply; raise only one of them.", "untouched")
    if st["quad_view"]:
        if o.get("VR.bloom"):
            yield "warn", 3, "Bloom is on together with quad views; it shows visible seams around the sharp area."
        if o.get("graphics.LensEffects"):
            yield "warn", 2, "Lens effects are on together with quad views; they show visible seams around the sharp area."
        if machine["cpu_score"] < 55 and machine["gpu_score"] >= 60:
            yield ("warn", 4, "Quad views is on, but on this PC the processor is the limit, not the graphics card. "
                              "Quad views adds processor work and can lower the frame rate here.", "untouched")
    elif ratio < 1 and machine["gpu_score"] < machine["cpu_score"] + 15:
        how = ("tick Pimax OpenXR Quadviews in Pimax Play, then Use Quad Views in DCS's VR options"
               if st["runtime"] == "Pimax" else
               "it needs quad-views support in your headset software or the Quad-Views-Foveated add-on, "
               "then Use Quad Views in DCS's VR options")
        yield ("info", 0, "Quad views (foveated rendering) is off. It is the biggest single frame-rate gain "
                          f"in VR when the graphics card is the limit: {how}.", "untouched")
    if o.get("graphics.motionBlur"):
        yield "warn", 2, "Motion blur is on; in a headset it smears the picture and can cause discomfort."
    if o.get("graphics.DOF"):
        yield "warn", 2, "Depth of field is on; in a headset it blurs whatever you are not expected to look at."
    if o.get("graphics.AA") == "MSAA" and o.get("graphics.MSAA") == 2 and machine["gpu_score"] < 85:
        yield "warn", 5, "MSAA 4x in VR is very expensive at headset resolutions."
    if ratio < 0.9 and st["hires"] and (st["render_quality"] or 1.0) > 0.8:
        rq = f" (now {st['render_quality']:.2f})" if st["render_quality"] else ""
        yield ("info", 0, f"If DCS settings alone cannot hold the goal, lower render quality in {soft}{rq} "
                          "before lowering DCS pixel density.", "untouched")
    if len(st["refresh"]) > 1:
        yield ("info", 0, f"The goal assumes the headset runs at {st['target']} Hz. It can also run at "
                          + ", ".join(str(r) for r in st["refresh"] if r != st["target"])
                          + f" Hz ({soft}); set DCS's frame-rate limit to match.", "untouched")
