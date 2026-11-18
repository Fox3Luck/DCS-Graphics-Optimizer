# DCS Graphics Optimizer - Fox3 Managed Solutions Inc.
# Created 2026-11-18. The heat check: does the frame rate fall as the PC warms up? (beta issue #23)
"""Turn a heat check into a plain answer. The check flies the same scenes several times in a row with
the player's own settings, in one DCS session, about a quarter of an hour. Every lap shows the same
thing, so a frame rate that falls from lap to lap is the PC slowing down as it heats up (thermal
throttling), not the scenery. Alongside, the program samples what Windows and the graphics driver
tell it: graphics card temperature, clock and power (NVIDIA only), and how fast the processor is
allowed to run compared with its rated speed (any PC)."""
from __future__ import annotations

STEADY_PCT, SLOWS_PCT = 3.0, 6.0        # frame-rate drop first lap -> last laps: below = steady, above = slows
HOT_GPU_C = 84                          # most graphics cards start to slow themselves in the mid 80s
CLOCK_DROP_PCT = 4.0                    # graphics card clock or processor speed falling this much = slowed


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _between(samples, t0, t1, key):
    return _mean([s.get(key) for s in samples if t0 <= s["t"] <= t1 + 1])


def summarize(laps: list[dict], samples: list[dict], cap: int | None = None) -> dict:
    """laps: [{"avg_fps", "p1_low_fps", "t0", "t1"}] in flying order. samples: [{"t", "gpu_temp",
    "gpu_clock", "gpu_power", "cpu_speed"}], any value may be None or missing."""
    if len(laps) < 3:
        raise ValueError("a heat check needs at least three laps")
    rows = []
    for n, lap in enumerate(laps, 1):
        row = {"lap": n, "avg_fps": round(lap["avg_fps"], 1), "p1_low_fps": round(lap["p1_low_fps"], 1),
               "minute": round((lap["t1"] - laps[0]["t0"]) / 60, 1)}
        for key in ("gpu_temp", "gpu_clock", "gpu_power", "cpu_speed"):
            v = _between(samples, lap["t0"], lap["t1"], key)
            row[key] = round(v) if v is not None else None
        rows.append(row)
    first, last = rows[0]["avg_fps"], _mean([r["avg_fps"] for r in rows[-2:]])
    drop = round((first - last) / first * 100, 1) if first else 0.0
    low_first, low_last = rows[0]["p1_low_fps"], _mean([r["p1_low_fps"] for r in rows[-2:]])
    low_drop = round((low_first - low_last) / low_first * 100, 1) if low_first else 0.0
    temps = [s["gpu_temp"] for s in samples if s.get("gpu_temp") is not None]

    def fell(key):
        a, b = rows[0][key], _mean([r[key] for r in rows[-2:]])
        return round((a - b) / a * 100, 1) if a and b is not None else None
    out = {"laps": rows, "minutes": rows[-1]["minute"], "first_fps": first, "last_fps": round(last, 1),
           "drop_pct": drop, "low_drop_pct": low_drop,
           "gpu_temp_start": temps[0] if temps else None, "gpu_temp_peak": max(temps) if temps else None,
           "gpu_clock_drop_pct": fell("gpu_clock"), "cpu_speed_drop_pct": fell("cpu_speed")}
    out["verdict"] = "steady" if drop < STEADY_PCT else "slight" if drop < SLOWS_PCT else "slows"
    # At the frame-rate limit the whole way: the PC had power to spare, and a small loss would not show.
    out["cap"] = cap
    out["at_cap"] = bool(cap) and min(r["avg_fps"] for r in rows) >= cap * 0.97
    out["lines"] = _lines(out)
    return out


def _lines(h: dict) -> list[str]:
    span = f"over {h['minutes']:.0f} minutes" if h["minutes"] >= 2 else "over the check"
    lines = [f"Frame rate on the first lap: {h['first_fps']:.0f} FPS. On the last laps: {h['last_fps']:.0f} FPS "
             f"({'down' if h['drop_pct'] > 0 else 'up'} {abs(h['drop_pct']):.1f}% {span})."]
    if h["gpu_temp_peak"] is not None:
        lines.append(f"Graphics card: {h['gpu_temp_start']:.0f} °C at the start, {h['gpu_temp_peak']:.0f} °C at its hottest.")
    else:
        lines.append("Graphics card temperature: not available on this PC (it is read through the NVIDIA driver).")
    gpu_slowed = (h["gpu_clock_drop_pct"] or 0) >= CLOCK_DROP_PCT
    cpu_slowed = (h["cpu_speed_drop_pct"] or 0) >= CLOCK_DROP_PCT
    hot = h["gpu_temp_peak"] is not None and h["gpu_temp_peak"] >= HOT_GPU_C
    if h["verdict"] == "steady" and h.get("at_cap"):
        lines.append(f"Verdict: steady. This PC sat at the check's limit of {h['cap']} FPS the whole time, which is "
                     "twice your goal, so it has power to spare even when warm.")
    elif h["verdict"] == "steady":
        lines.append("Verdict: steady. This PC holds its frame rate as it warms up, so the test results stand "
                     "for long flights too.")
    if h["verdict"] == "steady":
        if hot:
            lines.append(f"The graphics card does run hot ({h['gpu_temp_peak']:.0f} °C). It kept its speed here, "
                         "but there is little room left on a warm day.")
        return lines
    word = "a little" if h["verdict"] == "slight" else "noticeably"
    lines.append(f"Verdict: this PC slows down {word} as it warms up. On a long flight expect about "
                 f"{h['last_fps']:.0f} FPS where the short test showed {h['first_fps']:.0f}.")
    causes = []
    if gpu_slowed or hot:
        causes.append("the graphics card" + (f" lowered its clock by {h['gpu_clock_drop_pct']:.0f}%" if gpu_slowed else
                                             f" reached {h['gpu_temp_peak']:.0f} °C"))
    if cpu_slowed:
        causes.append(f"Windows let the processor run {h['cpu_speed_drop_pct']:.0f}% slower than at the start")
    if causes:
        lines.append("What the readings show: " + "; ".join(causes) + ". Better cooling helps: clean the dust "
                     "filters and fans, check the case has air coming in, and on a laptop raise the back and use "
                     "its performance power mode.")
    else:
        lines.append("The readings this program can see do not show which part is slowing down. Cooling is "
                     "still the first thing to check: dust filters, fans, and air into the case.")
    lines.append("Until then, a lower frame-rate goal of about "
                 f"{max(30, int(h['last_fps'] * 0.95 // 5 * 5))} FPS will hold for a whole flight.")
    return lines
