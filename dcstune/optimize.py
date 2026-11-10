"""Pick the best-looking settings that hold the frame-rate target.

``choose`` is a pure search over the model. ``run`` drives real benchmark runs through
a ``measure(changes) -> summary`` callable, so it can be tested with a fake.
"""
from __future__ import annotations

from . import model as M

VRAM_BUDGET = 0.90          # of the card
HIT_MARGIN = 0.95           # measured 1% low must reach this share of target (run-to-run noise is ~3-6%)
MAX_CONFIRM_RUNS = 4


def config_changes(config: dict, rung: dict) -> dict:
    out = dict(config)
    out.update(rung["set"])
    return out


def choose(mdl: M.Model, target_fps: float, vram_total_mb: float, low_ratio: float = 0.75):
    """For each anti-aliasing/upscaling rung, start from everything at minimum and keep
    taking the setting upgrade with the most quality per millisecond that still fits;
    then keep the rung whose result looks best overall.
    low_ratio = (1% low fps) / (model fps); the budget is set on 1% lows.
    Returns (config, rung, feasible)."""
    budget_ms = 1000.0 / target_fps * low_ratio
    vram_budget = vram_total_mb * VRAM_BUDGET if vram_total_mb else float("inf")
    ladder = M.upscale_ladder(mdl.vendor)

    def cfg(idx):
        return {s["key"]: s["levels"][idx[s["key"]]]["v"] for s in M.SETTINGS}

    def fits(idx, rung):
        c = cfg(idx)
        return mdl.frame_ms(c, rung) <= budget_ms and mdl.vram_mb(c, rung) <= vram_budget

    best = None
    for rung in ladder:
        idx = {s["key"]: 0 for s in M.SETTINGS}
        if not fits(idx, rung):
            continue
        while True:
            base_ms, base_q = mdl.frame_ms(cfg(idx), rung), mdl.quality(cfg(idx), rung)
            step = None
            for s in M.SETTINGS:
                key = s["key"]
                if idx[key] + 1 >= len(s["levels"]):
                    continue
                trial = dict(idx)
                trial[key] += 1
                if not fits(trial, rung):
                    continue
                dq = mdl.quality(cfg(trial), rung) - base_q
                if dq <= 0:
                    continue
                value = dq / max(mdl.frame_ms(cfg(trial), rung) - base_ms, 1e-3)
                if step is None or value > step[0]:
                    step = (value, key)
            if step is None:
                break
            idx[step[1]] += 1
        q = mdl.quality(cfg(idx), rung)
        if best is None or q > best[0]:
            best = (q, cfg(idx), rung)
    if best is None:   # nothing holds the target: everything at minimum, fastest rung
        return cfg({s["key"]: 0 for s in M.SETTINGS}), ladder[-1], False
    return best[1], best[2], True


def pick_target(mdl: M.Model, display_target: int, vram_total_mb: float, low_ratio: float) -> int:
    """Automatic goal. Prefer the display's refresh rate, but if holding it would strip
    the image below half of maximum quality, settle for a lower smooth rate instead."""
    steps = [t for t in (display_target, 90, 72, 60) if t <= display_target]
    top = M.max_quality(mdl.vendor)
    for t in steps:
        config, rung, feasible = choose(mdl, t, vram_total_mb, low_ratio)
        if feasible and mdl.quality(config, rung) >= 0.5 * top:
            return t
    return steps[-1]


def summarise(result: dict) -> dict:
    """Collapse a benchmark result into the numbers the optimizer steers by:
    the worst scene's 1% low, and the mean of scene averages."""
    scenes = result["scenes"]
    return {"p1_low_fps": min(s["p1_low_fps"] for s in scenes),
            "avg_fps": sum(s["avg_fps"] for s in scenes) / len(scenes),
            "vram_peak_mb": result.get("vram_peak_mb"),
            "scenes": scenes}


def run(mdl: M.Model, current: dict, vendor: str, target_fps: float, vram_total_mb: float,
        measure, full: bool = False, log=print) -> dict:
    """current: the player's flat options. measure(changes|None) -> summarise()d result
    (None = benchmark the player's settings untouched)."""
    cur_rung = M.current_rung(current, vendor)
    log("Measuring your current settings...")
    before = measure(None)
    low_ratio = max(0.4, min(0.95, before["p1_low_fps"] / before["avg_fps"]))
    mdl.calibrate(current, cur_rung, before["avg_fps"], before.get("vram_peak_mb"))

    if full:
        _measure_costs(mdl, current, cur_rung, before, measure, log)
    display_target = target_fps
    target_fps = pick_target(mdl, display_target, vram_total_mb, low_ratio)
    if target_fps < display_target:
        log(f"Holding {display_target} FPS would cost too much image quality on this PC; aiming for {target_fps}.")

    history, best = [], None
    for attempt in range(1, MAX_CONFIRM_RUNS + 1):
        config, rung, feasible = choose(mdl, target_fps, vram_total_mb, low_ratio)
        changes = config_changes(config, rung)
        if history and changes == history[-1]["changes"]:
            break
        log(f"Testing candidate {attempt} ({rung['name']})...")
        after = measure(changes)
        entry = {"changes": changes, "rung": rung["name"], "result": after,
                 "quality": mdl.quality(config, rung), "feasible": feasible,
                 "hit": after["p1_low_fps"] >= target_fps * HIT_MARGIN}
        history.append(entry)
        if entry["hit"] and (best is None or entry["quality"] > best["quality"]):
            best = entry
        # learn from the miss/overshoot and try again
        mdl.calibrate(config, rung, after["avg_fps"], after.get("vram_peak_mb"))
        low_ratio = max(0.4, min(0.95, after["p1_low_fps"] / after["avg_fps"]))
        if entry["hit"] and after["p1_low_fps"] < target_fps * 1.12:
            break
        if not feasible and attempt >= 2:
            break
    if best is None and history:   # target unreachable: recommend the fastest thing we saw
        best = max(history, key=lambda e: e["result"]["p1_low_fps"])
    cur_quality = mdl.quality(current, cur_rung)
    keep_current = (before["p1_low_fps"] >= target_fps * HIT_MARGIN and best is not None
                    and cur_quality >= best["quality"])
    return {"before": before, "recommended": None if keep_current else best,
            "keep_current": keep_current, "current_quality": cur_quality,
            "max_quality": M.max_quality(vendor), "target_fps": target_fps,
            "display_target": display_target, "history": history,
            "learned": {"calibration": mdl.calibration, "vram_offset": mdl.vram_offset, "low_ratio": low_ratio,
                        "measured": {k: {str(i): ms for i, ms in v.items()} for k, v in mdl.measured.items()}},
            "target_reached": bool(best and best["hit"]) or keep_current}


def _measure_costs(mdl, current, cur_rung, before, measure, log):
    """Full mode: measure what each setting's lowest and highest level really cost on
    this PC, one at a time against the player's own settings."""
    base_ms = 1000.0 / before["avg_fps"]
    for s in M.SETTINGS:
        key = s["key"]
        cur_i = M.level_index(s, current.get(key, s["levels"][0]["v"]))
        ms_at = {cur_i: base_ms}
        for i in {0, len(s["levels"]) - 1} - {cur_i}:
            log(f"Measuring {s['label']} = {s['levels'][i]['name']}...")
            r = measure({key: s["levels"][i]["v"]})
            ms_at[i] = 1000.0 / r["avg_fps"]
        for i, ms in ms_at.items():
            mdl.record_cost(key, i, ms - ms_at[0])
    # measured costs replace priors, so re-anchor the model on the baseline
    mdl.calibrate(current, cur_rung, before["avg_fps"])


def describe_changes(current: dict, changes: dict) -> list[dict]:
    """Plain-language list of what would change."""
    labels = {s["key"]: s for s in M.SETTINGS}
    out = []
    for key, new in sorted(changes.items()):
        old = current.get(key)
        if old == new:
            continue
        s = labels.get(key)
        if s:
            numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (old, new))
            order = [lv["v"] for lv in s["levels"]]
            ascending = not numeric or order == sorted(order)
            if numeric and ascending:
                up = new > old
            else:
                up = M.level_index(s, new) > M.level_index(s, old)
            out.append({"key": key, "label": s["label"], "from": M.level_name(s, old),
                        "to": M.level_name(s, new), "direction": "up" if up else "down"})
        else:
            out.append({"key": key, "label": key.split(".", 1)[1], "from": old, "to": new, "direction": ""})
    return out
