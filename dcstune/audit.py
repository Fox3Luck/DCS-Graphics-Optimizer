"""The audit file: one small JSON written into every saved report folder, so a tester can send
back what the tool saw and measured. It holds hardware, DCS and VR set-up, the graphics and VR
settings, and the test results. It holds no names, no folder paths, no account details, and the
tool never sends it anywhere: the player decides whether to share the report folder."""
from __future__ import annotations

import json
import time
from pathlib import PureWindowsPath

from . import __version__
from . import vr as V

SCHEMA = "dcsgo-audit/1"
# Values from the headset software that describe rendering. Body measurements (eye distance) are left out.
PIMAX_KEYS = ("pixels_per_display_pixel_rate", "enable_foveated_rendering", "gpu_upscaling_sharpness")
RESULT_KEYS = ("id", "kind", "duration_min", "runs", "target_fps", "target_reached", "keep_current", "disturbed",
               "vr", "vr_skipped", "before_result", "after_result", "changes", "costs",
               "overall_before", "overall_after")


def _stem(path) -> str:
    """File name without folder or extension - folders can contain the Windows user name."""
    return PureWindowsPath(str(path or "")).stem


def _gpu(g) -> dict | None:
    return {k: g.get(k) for k in ("name", "driver", "vram_mb", "width", "height", "refresh")} if isinstance(g, dict) else None


def _grade(card) -> dict | None:
    return {"grade": card.get("grade"), "score": card.get("score"), "basis": card.get("basis")} if isinstance(card, dict) else None


def build(info: dict, options: dict, report: dict, install: dict | None = None) -> dict:
    """info: sysinfo.collect(); options: flat options ({"graphics.x": v, "VR.x": v}); report: the test report."""
    raw_vr = info.get("vr") or {}
    found = V.detect(raw_vr)
    found["layers"] = [_stem(x) for x in found.get("layers", [])]
    try:
        profile = json.loads(raw_vr.get("pimax_profile") or "")
    except ValueError:
        profile = None
    pimax = None
    if isinstance(profile, dict):
        pimax = {"models": sorted(k[len("Pimax "):] for k in profile if k.startswith("Pimax ")),
                 "values": {k: profile[k] for k in PIMAX_KEYS if isinstance(profile.get(k), (int, float, bool))}}
    st = V.state(info, options)
    install = install or {}
    return {
        "schema": SCHEMA, "tool_version": __version__, "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "hardware": {
            "cpu": info.get("cpu"), "cores": info.get("cores"), "ram_gb": info.get("ram_gb"),
            "gpu": _gpu(info.get("gpu")),                                  # the one driving the display
            "gpus": [_gpu(g) for g in info.get("gpus") or []],
        },
        "dcs": {k: install.get(k) for k in ("version", "variant", "mt", "media")},
        "vr": {
            "enabled": bool(options.get("VR.enable")),
            "runtime_file": _stem(raw_vr.get("runtime")) or None,
            "detected": found, "pimax": pimax,
            "rated_as": st and {k: st.get(k) for k in ("headset", "known", "eye_w", "eye_h", "refresh", "eye_tracking",
                                                        "render_quality", "pixel_density", "quad_view", "target", "steps")},
            "options": {k[3:]: v for k, v in sorted(options.items()) if k.startswith("VR.") and "ipd" not in k.lower()},
        },
        "graphics": {k[9:]: v for k, v in sorted(options.items()) if k.startswith("graphics.")},
        "pc_rating": _grade(report.get("machine")),
        "settings_rating_before": _grade(report.get("before")),
        "settings_rating_after": _grade(report.get("after")),
        "test": {k: report.get(k) for k in RESULT_KEYS if k in report},
    }


def text(info: dict, options: dict, report: dict, install: dict | None = None) -> str:
    return json.dumps(build(info, options, report, install), indent=1, default=str)
