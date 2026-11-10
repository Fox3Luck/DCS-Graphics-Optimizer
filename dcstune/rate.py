"""Scorecard: how capable is this PC for DCS, and how well do the settings fit it."""
from __future__ import annotations

import json
from pathlib import Path

from . import model as M
from .sysinfo import gpu_vendor

CALIBRATION_NAME = "dcstune-calibration.json"


def _fingerprint(info: dict, options: dict) -> dict:
    gpu = info.get("gpu") or {}
    return {"gpu": gpu.get("name"), "cpu": info.get("cpu"),
            "width": options.get("graphics.width"), "height": options.get("graphics.height")}


RESULT_KEYS = ("graphics.Upscaling", "graphics.AA", "graphics.DLSS_PerfQuality", "graphics.MSAA",
               "graphics.Scaling", "graphics.width", "graphics.height")
MAX_RESULTS = 24


def config_key(options: dict) -> str:
    """Identifies one combination of the settings that decide frame rate, so a later
    scorecard can recognise settings that were actually measured."""
    import hashlib
    def norm(v):
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v
    keys = [s["key"] for s in M.SETTINGS] + list(RESULT_KEYS)
    return hashlib.sha1(json.dumps([[k, norm(options.get(k))] for k in sorted(keys)]).encode()).hexdigest()[:16]


def save_calibration(profile: dict, info: dict, options: dict, learned: dict,
                     results: list[tuple[dict, dict]] = ()) -> None:
    """Keep what a benchmark learned about this PC so later no-benchmark scorecards
    are estimated from real measurements instead of the generic hardware table.
    results: (flat options, measured summary) pairs from this test; they are kept so
    that settings which were really measured are shown with their measured numbers."""
    from .optionslua import atomic_write
    old = load_calibration(profile, info, options) or {}
    kept = dict(old.get("results") or {})
    for opts, res in results:
        kept.pop(config_key(opts), None)       # re-insert so the newest are last
        kept[config_key(opts)] = {k: res.get(k) for k in ("p1_low_fps", "avg_fps", "vram_peak_mb")}
    data = dict(learned, fingerprint=_fingerprint(info, options),
                results=dict(list(kept.items())[-MAX_RESULTS:]))
    atomic_write(Path(profile["path"]) / "Config" / CALIBRATION_NAME, json.dumps(data).encode())


def load_calibration(profile: dict, info: dict, options: dict) -> dict | None:
    """None unless a saved calibration exists for this same hardware and resolution."""
    path = Path(profile["path"]) / "Config" / CALIBRATION_NAME
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if data.get("fingerprint") == _fingerprint(info, options) else None


GRADES = [(85, "A"), (70, "B"), (55, "C"), (40, "D"), (0, "F")]


def grade(score: float) -> str:
    return next(g for cut, g in GRADES if score >= cut)


def target_fps(refresh: int | None) -> int:
    """Automatic goal: hold the display's refresh rate on 1% lows, within 60-120."""
    return max(60, min(int(refresh or 60), 120))


def hardware_summary(info: dict) -> list[dict]:
    """The PC at a glance, as label/value rows for the scorecard."""
    gpu = info.get("gpu") or {}
    inst = (info.get("installs") or [{}])[0]
    rows = [("Graphics card", gpu.get("name") or "unknown"),
            ("Video memory", f"{(gpu.get('vram_mb') or 0) / 1024:.0f} GB" if gpu.get("vram_mb") else "unknown"),
            ("Processor", (info.get("cpu") or "unknown")
             + (f" ({info['cores']} cores)" if info.get("cores") else "")),
            ("Memory", f"{info.get('ram_gb')} GB" if info.get("ram_gb") else "unknown"),
            ("Display", f"{gpu['width']} x {gpu['height']} at {gpu.get('refresh') or '?'} Hz" if gpu.get("width") else "unknown")]
    media = (inst.get("media") or "").upper()
    if media in ("SSD", "HDD"):
        rows.append(("DCS drive", "SSD" if media == "SSD" else "Hard disk"))
    if inst.get("version"):
        rows.append(("DCS version", inst["version"]))
    return [{"label": k, "value": v} for k, v in rows]


OVERALL_PC_WEIGHT = 0.4      # the rest is how well the settings use the PC


def overall(machine: dict, settings: dict) -> dict:
    """One headline number: 40% what the PC can do, 60% how well the settings use it."""
    score = OVERALL_PC_WEIGHT * machine["score"] + (1 - OVERALL_PC_WEIGHT) * settings["score"]
    return {"score": round(score), "grade": grade(score), "basis": settings["basis"]}


def flat_options(opts) -> dict:
    out = {}
    for section in ("graphics", "VR"):
        for k, v in opts.section(section).items():
            out[f"{section}.{k}"] = v
    return out


def rate_machine(info: dict) -> dict:
    gpu = info.get("gpu") or {}
    g, g_known = M.tier_score("gpu", gpu.get("name"))
    c, c_known = M.tier_score("cpu", info.get("cpu"))
    ram = info.get("ram_gb") or 0
    vram = (gpu.get("vram_mb") or 0) / 1024
    ram_score = 100 if ram >= 60 else 85 if ram >= 32 else 45 if ram >= 16 else 15
    vram_score = min(100, vram / 16 * 100)
    score = 0.42 * g + 0.38 * c + 0.10 * ram_score + 0.10 * vram_score
    reasons = [
        f"Graphics card: {gpu.get('name', 'unknown')} ({vram:.0f} GB) - {_word(g)}"
        + ("" if g_known else " (not in our table yet, estimated)"),
        f"Processor: {info.get('cpu', 'unknown')} - {_word(c)} single-thread speed, which is what limits DCS"
        + ("" if c_known else " (not in our table yet, estimated)"),
        f"Memory: {ram} GB - " + ("plenty" if ram >= 60 else "good" if ram >= 32 else
                                  "tight for DCS; 32 GB or more avoids stutter" if ram >= 16 else "too little for DCS"),
    ]
    return {"score": round(score), "grade": grade(score), "reasons": reasons,
            "gpu_score": g, "cpu_score": c, "estimated": not (g_known and c_known)}


def _word(score: int) -> str:
    return ("top tier" if score >= 85 else "high end" if score >= 65 else "mid range"
            if score >= 45 else "entry level" if score >= 25 else "below DCS's comfortable minimum")


def rate_settings(info: dict, options: dict, machine: dict, measured: dict | None = None,
                  target: int | None = None, calibration: dict | None = None) -> dict:
    """options: flat dict from flat_options(). measured: optional benchmark summary
    {"p1_low_fps", "avg_fps", "vram_peak_mb"}."""
    gpu = info.get("gpu") or {}
    vendor = gpu_vendor(info)
    width = options.get("graphics.width") or gpu.get("width") or 1920
    height = options.get("graphics.height") or gpu.get("height") or 1080
    mdl = M.Model(machine["gpu_score"], machine["cpu_score"], width, height, vendor)
    low_ratio, est_basis = 0.75, "estimated"   # generic: 1% lows in DCS run ~25% under typical
    if calibration:
        mdl.calibration, mdl.vram_offset = calibration["calibration"], calibration["vram_offset"]
        mdl.measured = {k: {int(i): ms for i, ms in v.items()} for k, v in calibration.get("measured", {}).items()}
        low_ratio, est_basis = calibration["low_ratio"], "estimated from your last test"
    rung = M.current_rung(options, vendor)
    target = target or target_fps(gpu.get("refresh"))
    vram_total = gpu.get("vram_mb") or 0

    if not measured and calibration:
        # These exact settings were benchmarked in an earlier test: show that, not a guess.
        seen = (calibration.get("results") or {}).get(config_key(options))
        if seen and seen.get("p1_low_fps"):
            measured, est_basis = seen, "measured in your last test"
    if measured:
        fps, vram_used = measured["p1_low_fps"], measured.get("vram_peak_mb")
        basis = est_basis if est_basis.startswith("measured") else "measured"
    else:
        fps, vram_used, basis = mdl.fps(options, rung) * low_ratio, mdl.vram_mb(options, rung), est_basis
    ratio = fps / target
    share = mdl.quality(options, rung) / M.max_quality(vendor)

    score, findings = 100.0, []
    if ratio < 1:
        score -= min(60, (1 - ratio) * 130)
        if ratio >= 0.9:
            findings.append(("warn", f"Frame rate dips to about {fps:.0f} FPS ({basis}), "
                                     f"just short of the {target} your display can show."))
        else:
            findings.append(("bad", f"Frame rate dips to about {fps:.0f} FPS ({basis}); "
                                    f"your display wants {target}. Settings ask more than this PC can hold."))
    else:
        findings.append(("good", f"Holds about {fps:.0f} FPS in the worst moments ({basis}) "
                                 f"against a {target} FPS goal."))
    if ratio > 1.25 and share < 0.8:
        score -= (0.8 - share) * 60 * min(1.0, (ratio - 1.25) / 0.5 + 0.4)
        findings.append(("warn", f"About {min(99, (ratio - 1) * 100):.0f}% performance is going unused while image "
                                 f"quality sits at {share * 100:.0f}% of maximum. DCS could look better at no cost you would feel."))
    if vram_total and vram_used and vram_used > 0.92 * vram_total:
        score -= 15
        findings.append(("bad", f"Video memory is nearly full ({vram_used / 1024:.1f} of {vram_total / 1024:.0f} GB, "
                                f"{basis}); this causes stutter when new scenery loads."))

    untouched = set()      # findings about things this tool never changes
    for sev, penalty, text, *tag in _rules(info, options, machine, gpu, ratio):
        score -= penalty
        findings.append((sev, text))
        if tag:
            untouched.add(text)

    score = max(0, min(100, score))
    return {"score": round(score), "grade": grade(score), "basis": basis, "target_fps": target,
            "fps": round(fps, 1), "quality_share": round(share, 3),
            "vram_mb": round(vram_used) if vram_used else None,
            "aa": rung["name"], "findings": [{"severity": s, "text": t} | ({"untouched": True} if t in untouched else {})
                                         for s, t in findings]}


def _rules(info, o, machine, gpu, ratio):
    g = lambda k, d=None: o.get("graphics." + k, d)
    vram_gb = (gpu.get("vram_mb") or 0) / 1024
    ram = info.get("ram_gb") or 0
    if o.get("VR.enable"):
        yield "info", 0, "VR is switched on. This version tunes flat-screen settings only; VR tuning comes in the next version.", "untouched"
    dw, dh = gpu.get("width"), gpu.get("height")
    if dw and dh and g("width") and (g("width") > dw or g("height") > dh):
        yield "warn", 6, (f"DCS is set to {g('width')}x{g('height')} but the desktop is {dw}x{dh}. "
                          "The extra pixels are rendered and then thrown away or pushed off-screen."), "untouched"
    if vram_gb >= 12 and g("textures") is not None and g("textures") < 2:
        yield "warn", 5, f"Textures are not on High although the card has {vram_gb:.0f} GB of video memory to hold them."
    if vram_gb >= 12 and g("terrainTextures") == "min":
        yield "warn", 4, f"Terrain textures are on Low; a {vram_gb:.0f} GB card shows the High set with no frame-rate cost."
    if vram_gb and vram_gb < 8 and g("textures") == 2:
        yield "bad", 8, f"High textures on a {vram_gb:.0f} GB card overflow video memory in most modules."
    if ram and ram < 32 and (g("preloadRadius") or 0) > 60000:
        yield "warn", 5, f"Preload radius is {g('preloadRadius')} with {ram} GB of memory; this can push Windows into swapping.", "untouched"
    if ram >= 48 and (g("preloadRadius") or 0) < 60000:
        yield "info", 2, "Preload radius is low for a PC with this much memory; raising it reduces pop-in stutter.", "untouched"
    if g("Upscaling") == "DLSS" and (g("DLSS_PerfQuality") or 0) >= 3 and (g("height") or 0) <= 1440:
        yield "warn", 5, "DLSS Performance at this resolution makes cockpit text and distant aircraft blurry."
    if g("Upscaling") in ("DLSS", "FSR", "NIS") and ratio > 1.4:
        yield "info", 3, "Upscaling is on although the PC has room to render at full resolution, which is sharper."
    if g("AA") == "MSAA" and g("MSAA") == 2 and machine["gpu_score"] < 60 and g("Upscaling", "OFF") == "OFF":
        yield "warn", 4, "MSAA 4x is the most expensive anti-aliasing mode in DCS for this class of card."
    if g("AA", "OFF") == "OFF" and g("Upscaling", "OFF") == "OFF":
        yield "warn", 4, "Anti-aliasing is off; edges and distant aircraft shimmer."
    if g("anisotropy") is not None and g("anisotropy") < 3 and machine["gpu_score"] >= 30:
        yield "info", 2, "Anisotropic filtering is low; 16x sharpens runways and ground textures almost for free."
    if machine["gpu_score"] < 45:
        heavy = [n for n in ("SSAO", "SSLR", "SSS") if g(n)]
        if heavy:
            yield "warn", 4, f"{', '.join(heavy)} cost a lot on this graphics card for a small visual gain."
    for inst in info.get("installs", []):
        if (inst.get("media") or "").upper() == "HDD":
            yield "warn", 4, "DCS is installed on a hard disk; an SSD removes most loading stutter."
            break
