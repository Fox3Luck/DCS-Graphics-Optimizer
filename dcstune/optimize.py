"""Pick the best-looking settings that hold the frame-rate target.

``choose`` is a pure search over the model. ``run`` drives real benchmark runs through
a ``measure(changes) -> summary`` callable, so it can be tested with a fake.
"""
from __future__ import annotations

from . import model as M
from . import vr as V

VRAM_BUDGET = 0.90          # of the card
HIT_MARGIN = 0.95           # measured 1% low must reach this share of target (run-to-run noise is ~3-6%)
MAX_CONFIRM_RUNS = 4
AIM_ABOVE = 1.04            # plan for a little more than the goal; real runs land a few percent either side
MIN_GAIN = 0.03             # share of maximum image quality a change must add to be worth recommending


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


def pick_target(mdl: M.Model, display_target: int, vram_total_mb: float, low_ratio: float,
                steps: list[int] | None = None) -> int:
    """Automatic goal. Prefer the display's refresh rate, but if holding it would strip
    the image below half of maximum quality, settle for a lower smooth rate instead.
    steps: the rates to fall back through (a VR headset's own refresh rates)."""
    steps = [t for t in (steps or (display_target, 90, 72, 60)) if t <= display_target]
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
        measure, full: bool = False, log=print, measure_fast=None, measure_batch=None,
        steps: list[int] | None = None, extra: dict | None = None) -> dict:
    """current: the player's flat options. measure(changes|None) -> summarise()d result
    (None = benchmark the player's settings untouched).
    steps: goals to fall back through (VR). extra: changes that are part of every
    candidate whatever the search picks (VR: pixel density 1.0, effects that break in a headset)."""
    cur_rung = M.current_rung(current, vendor)
    log("Measuring your current settings...")
    before = measure(None)
    low_ratio = max(0.4, min(0.95, before["p1_low_fps"] / before["avg_fps"]))
    mdl.calibrate(current, cur_rung, before["avg_fps"], before.get("vram_peak_mb"))

    disturbed = False
    if full:
        disturbed = _measure_costs(mdl, current, cur_rung, before, measure, measure_fast, log, measure_batch)
    display_target = target_fps
    target_fps = pick_target(mdl, display_target, vram_total_mb, low_ratio, steps)
    if target_fps < display_target:
        log(f"Holding {display_target} FPS would cost too much image quality on this PC; aiming for {target_fps}.")

    cur_hits = before["p1_low_fps"] >= target_fps * HIT_MARGIN
    need = target_fps if cur_hits else target_fps * HIT_MARGIN     # what a candidate must measure
    history, best = [], None
    for attempt in range(1, MAX_CONFIRM_RUNS + 1):
        config, rung, feasible = choose(mdl, target_fps * AIM_ABOVE, vram_total_mb, low_ratio)
        changes = config_changes(config, rung)
        changes.update(extra or {})
        if history and changes == history[-1]["changes"]:
            break
        log(f"Testing candidate {attempt} ({rung['name']})...")
        after = measure(changes)
        entry = {"changes": changes, "rung": rung["name"], "result": after,
                 "quality": mdl.quality(config, rung), "feasible": feasible,
                 "hit": after["p1_low_fps"] >= need}
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
    cur_quality = mdl.quality(current, cur_rung)
    # When the player's settings already hold the goal, only replace them with something
    # that is clearly better looking AND holds the goal outright (no noise allowance):
    # otherwise the "recommendation" would be a sideways or downward step.
    clearly_better = (best is not None
                      and best["quality"] >= cur_quality + MIN_GAIN * M.max_quality(vendor)
                      and best["result"]["p1_low_fps"] >= need)
    keep_current = cur_hits and not clearly_better
    if best is None and not cur_hits and history:
        # Nothing holds the goal: offer the smoothest thing measured, but only if it is
        # really smoother than what the player already has.
        fastest = max(history, key=lambda e: e["result"]["p1_low_fps"])
        if fastest["result"]["p1_low_fps"] > before["p1_low_fps"] * 1.03:
            best = fastest
    if keep_current or best is None:
        recommended, keep_current = None, True
    else:
        recommended = best
    return {"before": before, "recommended": recommended,
            "keep_current": keep_current, "current_quality": cur_quality,
            "max_quality": M.max_quality(vendor), "target_fps": target_fps,
            "display_target": display_target, "history": history,
            "disturbed": disturbed,
            "learned": {"calibration": mdl.calibration, "vram_offset": mdl.vram_offset, "low_ratio": low_ratio,
                        "measured": {k: {str(i): ms for i, ms in v.items()} for k, v in mdl.measured.items()}},
            "target_reached": cur_hits or bool(best and best["hit"])}


RECHECK_EVERY = 5        # cost runs between baseline re-checks (restart-per-run path)
BATCH_SIZE = 16          # settings changes per DCS launch (no-restart path)
DRIFT_LIMIT = 0.05       # baseline moved more than this -> something else was using the PC


def _measure_costs(mdl, current, cur_rung, before, measure, measure_fast, log, measure_batch=None) -> bool:
    """Full mode: measure what each setting's lowest and highest level really cost on
    this PC, one at a time against the player's own settings. Settings marked
    "measure": false cost too little to be worth measuring and keep their estimate.

    Two ways of measuring:
    - measure_batch (preferred): several changes in ONE DCS launch, restarting only the
      mission. Each batch starts and ends with the player's own settings, so a shift in
      the PC's speed during the batch is caught and the batch is thrown away.
    - one DCS launch per change, for settings DCS only applies after a restart
      ("restart": true) or when no batch function is given. The baseline is re-measured
      every few runs for the same reason.
    Discarded settings fall back to the built-in estimate. Returns True if any were."""
    base_ms = 1000.0 / before["avg_fps"]
    disturbed = False

    def commit(s, ms_at):
        nonlocal disturbed
        # sanity: turning a setting DOWN cannot make DCS clearly slower
        if any(ms_at[i] > ms_at[j] * 1.03 for i in ms_at for j in ms_at if i < j):
            log(f"  {s['label']}: measurements do not make sense (lower was slower); using the estimate")
            disturbed = True
            return
        if 0 in ms_at and len(ms_at) > 1:
            for i, ms in ms_at.items():
                mdl.record_cost(s["key"], i, ms - ms_at[0])

    jobs = []                                   # (setting, level index, current index)
    for s in M.SETTINGS:
        if s.get("measure") is False:
            continue
        cur_i = M.level_index(s, current.get(s["key"], s["levels"][0]["v"]))
        for i in sorted({0, len(s["levels"]) - 1} - {cur_i}):
            jobs.append((s, i, cur_i))
    batched = [j for j in jobs if measure_batch is not None and not j[0].get("restart")]
    single = [j for j in jobs if j not in batched]

    # ---- no-restart batches ------------------------------------------------------
    deltas: dict[str, dict[int, float]] = {}    # key -> level -> ms relative to the player's settings
    for n in range(0, len(batched), BATCH_SIZE):
        chunk = batched[n:n + BATCH_SIZE]
        log(f"Measuring {len(chunk)} settings changes in one DCS run: "
            + ", ".join(f"{s['label']} = {s['levels'][i]['name']}" for s, i, _ in chunk) + "...")
        try:
            res = measure_batch([None] + [{s["key"]: s["levels"][i]["v"]} for s, i, _ in chunk] + [None])
            ms = [1000.0 / r["avg_fps"] for r in res]
        except Exception as e:
            log(f"  this run failed ({e}); using built-in estimates for these settings")
            disturbed = True
            continue
        first, last = ms[0], ms[-1]
        if abs(first - last) / first > DRIFT_LIMIT:
            disturbed = True
            log("  The PC's speed changed during this run (another program was probably using it). "
                "Discarding it and using built-in estimates for these settings.")
            continue
        batch_base = (first + last) / 2
        for (s, i, _), m in zip(chunk, ms[1:-1]):
            deltas.setdefault(s["key"], {})[i] = m - batch_base
    for s in M.SETTINGS:
        if s["key"] in deltas:
            cur_i = M.level_index(s, current.get(s["key"], s["levels"][0]["v"]))
            ms_at = {cur_i: base_ms}
            ms_at.update({i: base_ms + d for i, d in deltas[s["key"]].items()})
            commit(s, ms_at)

    # ---- one DCS launch per change -------------------------------------------------
    if single:
        if measure_fast is not None:
            log("Measuring your current settings (short run)...")
            measure, base_ms = measure_fast, 1000.0 / measure_fast(None)["avg_fps"]
        pending, runs_since_check = [], 0

        def recheck():
            nonlocal base_ms, disturbed, pending, runs_since_check
            runs_since_check = 0
            if not pending:
                return
            log("Re-checking your current settings...")
            try:
                now_ms = 1000.0 / measure(None)["avg_fps"]
            except Exception as e:
                log(f"  re-check failed ({e}); discarding the last measurements")
                now_ms = None
            if now_ms is None or abs(now_ms - base_ms) / base_ms > DRIFT_LIMIT:
                disturbed = True
                log("  The PC's speed changed during these measurements (another program was probably "
                    "using it). Discarding them and using built-in estimates for: "
                    + ", ".join(s["label"] for s, _ in pending))
                if now_ms is not None:
                    base_ms = now_ms            # carry on from the new normal
            else:
                for s, ms_at in pending:
                    commit(s, ms_at)
            pending = []

        by_setting: dict[str, tuple] = {}
        for s, i, cur_i in single:
            by_setting.setdefault(s["key"], (s, cur_i, []))[2].append(i)
        for s, cur_i, levels in by_setting.values():
            ms_at = {cur_i: base_ms}
            for i in levels:
                log(f"Measuring {s['label']} = {s['levels'][i]['name']}...")
                try:
                    r = measure({s["key"]: s["levels"][i]["v"]})
                except Exception as e:      # one failed launch must not waste the whole test
                    log(f"  skipped ({e}); using the built-in estimate for this level")
                    continue
                ms_at[i] = 1000.0 / r["avg_fps"]
                runs_since_check += 1
            if len(ms_at) > 1:
                pending.append((s, ms_at))
            if runs_since_check >= RECHECK_EVERY:
                recheck()
        recheck()
    # measured costs replace priors, so re-anchor the model on the baseline
    mdl.calibrate(current, cur_rung, before["avg_fps"])
    return disturbed


RUNG_KEYS = ("graphics.Upscaling", "graphics.AA", "graphics.DLSS_PerfQuality", "graphics.MSAA", "graphics.Scaling")


def describe_changes(current: dict, changes: dict, vendor: str = "nvidia", mdl=None,
                     base_ms: float | None = None) -> list[dict]:
    """Plain-language list of what would change. With a model (and the measured frame
    time of the player's settings) each row also says what it costs on this PC:
    cost_pct = share of frame time added (negative = saved), cost_basis measured|estimate."""
    labels = {s["key"]: s for s in M.SETTINGS}
    rung0 = M.current_rung(current, vendor)
    ms0 = mdl.frame_ms(current, rung0) if mdl else None

    def cost(row, config, rung, measured):
        if mdl and ms0:
            row["cost_pct"] = round((mdl.frame_ms(config, rung) - ms0) / (base_ms or ms0) * 100, 1)
            row["cost_basis"] = "measured" if measured else "estimate"
        return row

    out = []
    after = dict(current)
    after.update(changes)
    rung1 = M.current_rung(after, vendor)
    rung_changed = any(current.get(k) != changes[k] for k in RUNG_KEYS if k in changes)
    grouped = rung_changed and rung0["name"] != rung1["name"]
    if grouped:      # the three or four DCS options behind this are one choice to a player
        up = rung1["quality"] > rung0["quality"]
        out.append(cost({"key": "upscaling", "label": "Upscaling and anti-aliasing", "from": rung0["name"],
                         "to": rung1["name"], "direction": "up" if up else "down",
                         "why": "Sharper picture: more of each frame is really drawn" if up
                                else "Draws fewer pixels per frame to free up frame rate"},
                        current, rung1, False))
    for key, new in sorted(changes.items()):
        old = current.get(key)
        if old == new or (grouped and key in RUNG_KEYS):
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
            row = {"key": key, "label": s["label"], "from": M.level_name(s, old),
                   "to": M.level_name(s, new), "direction": "up" if up else "down"}
            if mdl:
                row["why"] = s.get("why", "") if up else "Lowered to free up frame rate"
                cost(row, dict(current, **{key: new}), rung0, key in mdl.measured)
            out.append(row)
        elif V.fixed_row(key, old, new):
            row = V.fixed_row(key, old, new)
            if key == "VR.pixel_density":
                cost(row, dict(current, **{key: new}), rung0, False)
            out.append(row)
        else:
            out.append({"key": key, "label": key.split(".", 1)[1], "from": old, "to": new, "direction": ""})
    if mdl:
        out.sort(key=lambda r: (r["key"] != "upscaling", -(r.get("cost_pct") or 0), r["label"]))
    return out


def measured_costs(mdl, base_ms: float) -> list[dict]:
    """What each measured setting costs at its highest measured level compared with its
    lowest, as a share of the player's frame time. Most expensive first."""
    out = []
    for s in M.SETTINGS:
        m = mdl.measured.get(s["key"])
        if not m or len(m) < 2:
            continue
        top = max(m)
        out.append({"key": s["key"], "label": s["label"], "level": s["levels"][top]["name"],
                    "lowest": s["levels"][0]["name"], "cost_pct": round(m[top] / base_ms * 100, 1)})
    return sorted(out, key=lambda r: -r["cost_pct"])
