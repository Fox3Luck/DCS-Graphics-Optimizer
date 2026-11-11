"""Settings table + frame-time model shared by the rater and the optimizer.

A *config* is a dict of dotted option keys -> values, e.g. {"graphics.shadows": 3}.
The model predicts frame time for a config. It starts from bundled priors and is
corrected by real measurements (a global calibration factor, and per-setting
measured costs when a Full run has them).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DATA = Path(__file__).parent / "data"
TABLE = json.loads((DATA / "settings.json").read_text())
TIERS = json.loads((DATA / "hardware_tiers.json").read_text())
SETTINGS = TABLE["settings"]
BASE_VRAM_MB = 4500      # DCS with everything at minimum, 1440p, typical module
REF_PIXELS = 2560 * 1440


def tier_score(kind: str, name: str | None, default: int = 40) -> tuple[int, bool]:
    """Returns (score, known)."""
    for pattern, score in TIERS[kind]:
        if name and re.search(pattern, name, re.I):
            return score, True
    return default, False


def level_index(setting: dict, value) -> int:
    """Index of the level matching value (nearest for numeric sliders)."""
    levels = setting["levels"]
    for i, lv in enumerate(levels):
        if lv["v"] == value and not isinstance(value, bool):
            return i
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        nums = [(abs(lv["v"] - value), i) for i, lv in enumerate(levels)
                if isinstance(lv["v"], (int, float))]
        if nums:
            return min(nums)[1]
    return 0


def level_name(setting: dict, value) -> str:
    """Name of a value as the player sees it; slider values between our listed levels
    are shown as they really are, not rounded to the nearest level."""
    if value is None:
        return "unset"
    for lv in setting["levels"]:
        if lv["v"] == value and not isinstance(value, bool):
            return lv["name"]
    if "fmt" in setting and isinstance(value, (int, float)):
        return setting["fmt"].format(value * setting.get("mul", 1))
    return setting["levels"][level_index(setting, value)]["name"]


def upscale_ladder(vendor: str) -> list[dict]:
    return TABLE["upscale_ladder"]["nvidia" if vendor == "nvidia" else "other"]


def current_rung(options: dict, vendor: str) -> dict:
    """Describe the player's current AA/upscaling as a ladder-like rung."""
    up = options.get("graphics.Upscaling", "OFF")
    aa = options.get("graphics.AA", "OFF")
    if up == "DLSS":
        scale = {1: 0.667, 2: 0.58, 3: 0.5, 4: 0.333}.get(options.get("graphics.DLSS_PerfQuality"), 0.58)
        quality = {1: 32, 2: 26, 3: 18, 4: 8}.get(options.get("graphics.DLSS_PerfQuality"), 13)
        name = "DLSS " + {1: "Quality", 2: "Balanced", 3: "Performance", 4: "Ultra Performance"}.get(
            options.get("graphics.DLSS_PerfQuality"), "")
    elif up in ("FSR", "NIS"):
        scale = float(options.get("graphics.Scaling", 0.66))
        quality, name = 12 + 18 * (scale - 0.5) / 0.4, f"{up} {round(scale * 100)}%"
    elif aa == "MSAA":
        four = options.get("graphics.MSAA") == 2
        scale, quality, name = (1.15, 40, "MSAA 4x") if four else (1.07, 34, "MSAA 2x")
    elif aa in ("DLAA", "TAA"):
        scale, quality, name = 1.0, 40 if aa == "DLAA" else 34, f"{aa} (native)"
    else:
        scale, quality, name = 0.97, 16, "No anti-aliasing"
    return {"name": name.strip(), "render_scale": scale, "quality": quality, "set": {}}


def max_quality(vendor: str) -> float:
    return sum(s["levels"][-1]["quality"] for s in SETTINGS) + upscale_ladder(vendor)[0]["quality"]


class Model:
    def __init__(self, gpu_score: float, cpu_score: float, width: int, height: int,
                 vendor: str = "nvidia", vr: dict | None = None):
        """vr: None for a monitor, else {"eye_px", "render_quality", "pd"} (see vr.state);
        "pd" is the pixel density assumed for configs that do not carry one."""
        self.gpu_score, self.cpu_score = gpu_score, cpu_score
        self.pixels = width * height
        self.vr = vr
        self.vendor = vendor
        self.calibration = 1.0                  # measured_ms / predicted_ms
        self.vram_offset = 0.0                  # measured - predicted, MB
        self.measured: dict[str, dict[int, float]] = {}   # key -> level index -> ms delta vs level 0

    # -- prediction --------------------------------------------------------
    def _levels(self, config: dict):
        for s in SETTINGS:
            i = level_index(s, config[s["key"]]) if s["key"] in config else 0
            yield s, i, s["levels"][i]

    def quality(self, config: dict, rung: dict) -> float:
        return sum(lv["quality"] for _, _, lv in self._levels(config)) + rung["quality"]

    def _px(self, config: dict, rung: dict) -> float:
        """Pixels drawn per frame, in monitor-equivalent terms."""
        if not self.vr:
            return self.pixels * rung["render_scale"] ** 2
        from .vr import PIXEL_FACTOR, QUAD_FACTOR
        pd = config.get("VR.pixel_density", self.vr["pd"])
        px = 2 * self.vr["eye_px"] * (self.vr["render_quality"] * pd) ** 2 * PIXEL_FACTOR
        if config.get("VR.openxr_quadView", self.vr.get("quad")):
            px *= QUAD_FACTOR
        return px * rung["render_scale"] ** 2

    def frame_ms(self, config: dict, rung: dict) -> float:
        gpu_cost = cpu_cost = 0.0
        measured_ms = 0.0
        for s, i, lv in self._levels(config):
            m = self.measured.get(s["key"])
            if m is not None:
                measured_ms += _interp(m, i, s)
            else:
                gpu_cost += lv["gpu"]
                cpu_cost += lv["cpu"]
        px = self._px(config, rung)
        gpu_ms = 1000.0 / (self.gpu_score * 2.6) * (px / REF_PIXELS) ** 0.85 * (1 + gpu_cost)
        cpu_ms = 1000.0 / (self.cpu_score * 2.2) * (1 + cpu_cost)
        if self.vr:
            from .vr import CPU_FACTOR
            cpu_ms *= CPU_FACTOR
        return (max(gpu_ms, cpu_ms) + 0.3 * min(gpu_ms, cpu_ms)) * self.calibration + measured_ms

    def fps(self, config: dict, rung: dict) -> float:
        return 1000.0 / self.frame_ms(config, rung)

    def vram_mb(self, config: dict, rung: dict) -> float:
        px = self._px(config, rung)
        return (BASE_VRAM_MB + sum(lv["vram_mb"] for _, _, lv in self._levels(config))
                + 1200 * px / REF_PIXELS + self.vram_offset)

    # -- learning ----------------------------------------------------------
    def calibrate(self, config: dict, rung: dict, measured_fps: float,
                  measured_vram_mb: float | None = None) -> None:
        if measured_fps > 0:
            self.calibration *= (1000.0 / measured_fps) / self.frame_ms(config, rung)
        if measured_vram_mb:
            self.vram_offset += measured_vram_mb - self.vram_mb(config, rung)

    def record_cost(self, key: str, index: int, ms_delta_vs_level0: float) -> None:
        self.measured.setdefault(key, {0: 0.0})[index] = ms_delta_vs_level0


def _interp(measured: dict[int, float], i: int, setting: dict) -> float:
    """Measured ms for level i; unmeasured levels are placed between measured
    neighbors in proportion to the prior cost curve."""
    if i in measured:
        return measured[i]
    lo = max((k for k in measured if k < i), default=None)
    hi = min((k for k in measured if k > i), default=None)
    if lo is None:
        return measured[hi]
    if hi is None:
        return measured[lo]
    prior = lambda k: setting["levels"][k]["gpu"] + setting["levels"][k]["cpu"]
    span = prior(hi) - prior(lo)
    frac = (prior(i) - prior(lo)) / span if span else (i - lo) / (hi - lo)
    return measured[lo] + frac * (measured[hi] - measured[lo])
