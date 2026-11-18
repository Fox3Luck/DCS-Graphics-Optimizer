# DCS Graphics Optimizer - Fox3 Managed Solutions Inc.
# Created 2026-11-10. Turns a test report into the page shown in the window and saved for the player.
"""Turns a test report (the dict Engine.optimize saves) into HTML: a fragment shown in
the window and a self-contained page saved beside the screenshots for the player to
keep or share. One renderer, so the window and the saved report always agree."""
from __future__ import annotations

from html import escape as e

SCENE_LABELS = {"city": "City pass", "airfield": "Airfield ramp", "clouds": "Cloud layer", "busy": "Busy airfield"}

# Shared by the window and the saved page. A and B must not look the same.
CSS = """
:root { --bg:#10151c; --panel:#18202b; --line:#273342; --text:#e6edf5; --dim:#8fa1b5;
        --accent:#4cc2ff; --good:#4fd18b; --ok:#b9d64e; --warn:#f2b94b; --bad:#ff6b6b; }
@media (prefers-color-scheme: light) {
  :root { --bg:#f3f5f8; --panel:#fff; --line:#d9e0e8; --text:#17212c; --dim:#5b6b7c;
          --accent:#0b78c2; --good:#1c8f55; --ok:#6f8f12; --warn:#a86a00; --bad:#c43030; } }
.letter { width:56px; height:56px; border-radius:12px; display:inline-grid; place-items:center;
          font-size:30px; font-weight:700; color:#0c1117; }
.letter.sm { width:30px; height:30px; font-size:17px; border-radius:7px; vertical-align:middle; margin-right:8px; }
.A { background:var(--good); } .B { background:var(--ok); } .C { background:var(--warn); } .D,.F { background:var(--bad); }
.rep table { width:100%; border-collapse:collapse; }
.rep td, .rep th { text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); vertical-align:top; }
.rep th { color:var(--dim); font-weight:600; font-size:13px; }
.rep tr:last-child td { border-bottom:0; }
.rep .up { color:var(--good); font-weight:600; } .rep .down { color:var(--warn); font-weight:600; }
.rep .dim { color:var(--dim); } .rep .big { font-size:22px; font-weight:700; margin:0 0 6px; }
.rep .meta { color:var(--dim); margin:0 0 4px; }
.rep h3 { font-size:15px; margin:22px 0 8px; color:var(--dim); font-weight:600; }
.rep .note { border-left:3px solid var(--accent); padding:8px 12px; margin:10px 0; background:var(--bg); border-radius:0 8px 8px 0; }
.rep .note.err { border-color:var(--bad); }
.rep .scroll { overflow-x:auto; }
.rep .shots { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:12px; }
.rep .shots figure { margin:0; } .rep .shots img { width:100%; border-radius:8px; display:block; border:1px solid var(--line); }
.rep .shots figcaption { font-size:13px; color:var(--dim); padding-top:4px; }
.rep ul { margin:0; padding-left:18px; } .rep li { padding:3px 0; }
@media (max-width:560px) { .rep .shots { grid-template-columns:1fr; } }
"""


def gb(mb) -> str:
    return f"{mb / 1024:.1f} GB" if mb else "not measured"


def cost_text(row: dict, base_fps: float | None = None) -> str:
    """What one change costs. With the average frame rate of the player's own settings, a
    measured cost is also said in frames per second, since a percentage can be read two ways
    (#24). Estimates stay a percentage: turned into FPS, a rough estimate of a big saving
    becomes a wildly wrong number (a real run: estimate +261 FPS, measured +65)."""
    pct = row.get("cost_pct")
    if pct is None:
        return ""
    basis = "measured" if row.get("cost_basis") == "measured" else "estimate"
    if abs(pct) < 0.5:
        return f"Almost nothing ({basis})"
    word = "of frame rate" if pct > 0 else "frame rate gained"
    share = f"{abs(pct):.0f}%" if abs(pct) >= 10 else f"{abs(pct):.1f}%"
    fps = ""
    if base_fps and basis == "measured" and pct > -100:
        diff = round(base_fps / (1 + pct / 100) - base_fps)
        if diff:
            fps = f", {'+' if diff > 0 else '-'}{abs(diff)} FPS"
    return f"About {share} {word}{fps} ({basis})"


def _grade(card: dict | None) -> str:
    if not card:
        return ""
    return f'<span class="letter sm {e(card["grade"])}">{e(card["grade"])}</span>{card["score"]} / 100'


def _fps(v) -> str:
    return f"{v:.0f} FPS" if v else "not measured"


def _meta(rep: dict) -> str:
    bits = []
    if rep.get("kind"):
        bits.append(rep["kind"])
    if rep.get("scene"):                    # the player's own map and aircraft (#23)
        bits.append("flown with " + str(rep.get("scene_label")))
    if rep.get("busy"):                     # the fourth scene (#23, #35)
        bits.append("with the busy airfield scene")
    if rep.get("created"):
        bits.append(rep["created"])
    if rep.get("duration_min"):
        bits.append(f'{rep["duration_min"]} minutes')
    if rep.get("runs"):
        bits.append(f'DCS started {rep["runs"]} times')
    return " &middot; ".join(e(str(b)) for b in bits)


# Graphics card load (%) while a scene was timed, from Windows' counter. On the test PC (RTX 4080,
# Ryzen 9800X3D) 4K DLAA read 93-96% and everything turned down 89-90%.
GPU_BOUND, CPU_BOUND = 92, 75


def _limit(busy) -> str:
    if busy is None:
        return ""
    if busy >= GPU_BOUND:
        return "graphics card"
    if busy <= CPU_BOUND:
        return "processor"
    return "both about equally"


def _limits(res: dict) -> list[str]:
    """What held the frame rate back in each scene of the player's own settings (#31). The test
    switches vertical sync off and lifts the frame cap, so a graphics card that is not kept
    busy is waiting for the processor (DCS's simulation and the work of preparing each frame)."""
    scenes = [sc for sc in res.get("scenes") or [] if sc.get("gpu_busy") is not None]
    if not scenes:
        return []
    h = ['<h3>What limits your frame rate</h3><div class="scroll"><table><tr><th>Scene</th>'
         '<th>Graphics card busy</th><th>Held back by</th></tr>']
    for sc in scenes:
        h.append(f'<tr><td>{e(SCENE_LABELS.get(sc.get("name"), str(sc.get("name"))))}</td>'
                 f'<td>{sc["gpu_busy"]}%</td><td>{e(_limit(sc["gpu_busy"]))}</td></tr>')
    h.append("</table></div>")
    worst = min(scenes, key=lambda sc: sc.get("p1_low_fps") or 1e9)
    which = _limit(worst["gpu_busy"])
    where = e(SCENE_LABELS.get(worst.get("name"), str(worst.get("name"))).lower())
    if which == "graphics card":
        h.append(f'<p class="meta">In the slowest scene ({where}) your graphics card is working flat out. Graphics '
                 'settings such as resolution and upscaling, shadows and clouds are what move your frame rate; a '
                 'faster processor would not help much.</p>')
    elif which == "processor":
        h.append(f'<p class="meta">In the slowest scene ({where}) the graphics card is mostly waiting for the processor. '
                 'Lowering picture quality will not help much there; settings that add things to draw (visibility '
                 'range, civilian traffic, trees and scenery detail) ease it. Busy multiplayer servers and detailed '
                 'aircraft add more processor work, so expect lower frame rates there than in this test.</p>')
    else:
        h.append(f'<p class="meta">In the slowest scene ({where}) the graphics card and the processor are both near '
                 'their limit, so lowering either kind of setting helps a little.</p>')
    return h


def fragment(rep: dict, img=lambda name: name, pick: bool = False) -> str:
    """The test result. img(name) -> URL for a screenshot file of this report.
    pick: the window adds a tick box to each change so the player can leave some out (#24)."""
    before, after = rep.get("before") or {}, rep.get("after")
    br, ar = rep.get("before_result") or {}, rep.get("after_result") or {}
    has = bool(after and rep.get("changes"))
    ob, oa = rep.get("overall_before"), rep.get("overall_after")
    h = ['<div class="rep">']
    if has and ob and oa:
        h.append(f'<p class="big">Overall {e(ob["grade"])} ({ob["score"]}) &rarr; {e(oa["grade"])} ({oa["score"]})</p>')
    elif has:
        h.append(f'<p class="big">Grade {e(before.get("grade", "?"))} &rarr; {e(after["grade"])}</p>')
    else:
        h.append('<p class="big">Your settings are already the best match.</p>')
    if _meta(rep):
        h.append(f'<p class="meta">{_meta(rep)}</p>')
    if rep.get("target_fps"):
        h.append(f'<p class="meta">Goal: hold {rep["target_fps"]} FPS in the worst moments'
                 + (f' ({e(rep["mode_label"])})' if rep.get("mode_label") else '')
                 + (f', from your own goal of {int(rep["goal_chosen"])} FPS' if rep.get("goal_chosen") else '') + '.</p>')
    if rep.get("applied"):
        h.append(f'<p class="note">These settings were applied on {e(str(rep["applied"]))}. '
                 'Use Undo in the app to go back.</p>')
    if rep.get("vr_skipped"):
        h.append('<p class="note">VR is switched on in this DCS profile. This test ran on the monitor, so the '
                 'numbers below are monitor numbers, and no VR setting is changed. DCS uses the same graphics '
                 'settings in the headset, so applying these can make VR slower; the tool asks before it does.</p>')
    if rep.get("vr"):
        h.append('<p class="note">Measured in the VR headset.</p>')
    if rep.get("disturbed"):
        h.append('<p class="note err">Another program was using the PC during part of this test, so some '
                 'measurements were discarded. For the most accurate result, close other programs and run it again.</p>')
    if rep.get("vram_other_mb"):
        h.append(f'<p class="note err">Other programs were using {rep["vram_other_mb"] / 1024:.1f} GB of video memory '
                 'before DCS started. The video memory figures below include them, and the recommendation may be '
                 'more cautious than needed. For the most accurate result, close them and run the test again.</p>')
    if has and rep.get("target_reached") is False:
        h.append(f'<p class="note">This PC cannot hold {rep["target_fps"]} FPS in the heaviest scene; '
                 'this is the smoothest result measured.</p>')

    cols = [("Before" if has else "Your settings", before, br, ob)] + ([("Recommended", after, ar, oa)] if has else [])
    rows = [
        ("Settings grade", lambda c, r, o: _grade(c)),
        ("Overall score", lambda c, r, o: _grade(o)),
        ("Worst moments (1% low)", lambda c, r, o: _fps(r.get("p1_low_fps"))),
        ("Average frame rate", lambda c, r, o: _fps(r.get("avg_fps"))),
        ("Video memory at peak", lambda c, r, o: gb(r.get("vram_peak_mb"))),
        ("Image quality", lambda c, r, o: f'{c["quality_share"] * 100:.0f}% of maximum' if c.get("quality_share") is not None else ""),
        ("Upscaling and anti-aliasing", lambda c, r, o: e(str(c.get("aa") or ""))),
    ]
    h.append('<h3>Measured in DCS</h3><div class="scroll"><table><tr><th></th>'
             + "".join(f"<th>{name}</th>" for name, *_ in cols) + "</tr>")
    for label, fn in rows:
        cells = [fn(c, r, o) for _, c, r, o in cols]
        if any(cells):
            h.append(f"<tr><td>{label}</td>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    h.append("</table></div>")
    h.extend(_limits(br))

    changes = rep.get("change_list") or []
    if has and changes:
        extra = any("cost_pct" in c or c.get("why") for c in changes)
        pick = pick and not rep.get("applied") and len(changes) > 1
        skipped = set(rep.get("skipped") or ())
        base_fps = br.get("avg_fps")
        h.append('<h3>What changes, and what it costs on this PC</h3>')
        if pick:
            h.append('<p class="meta">Untick anything you would rather keep as it is, then press Apply. '
                     'The costs are on your average frame rate of ' + _fps(base_fps) + '.</p>')
        elif base_fps and extra:
            h.append(f'<p class="meta">The costs are on your average frame rate of {_fps(base_fps)}.</p>')
        only = len(changes) == 1 and base_fps and ar.get("avg_fps")
        h.append('<div class="scroll"><table><tr>' + ("<th>Apply</th>" if pick else "") + '<th>Setting</th>'
                 "<th>Now</th><th>Recommended</th>" + ("<th>What you get</th><th>Cost on this PC</th>" if extra else "") + "</tr>")
        for c in changes:
            box = (f'<td><input type="checkbox" class="pick" data-key="{e(str(c.get("key") or ""))}" '
                   f'aria-label="Apply {e(str(c["label"]))}" checked></td>') if pick else ""
            # A single change was measured on its own: say what DCS really did.
            cost = (f'Measured: {base_fps:.0f} to {ar["avg_fps"]:.0f} FPS average' if only
                    else cost_text(c, base_fps))
            kept = c.get("key") in skipped
            row_cls = ' class="dim"' if kept else ""
            h.append(f'<tr{row_cls}>{box}<td>{e(str(c["label"]))}'
                     + (" (not applied, kept as it was)" if kept else "") + f'</td><td>{e(str(c["from"]))}</td>'
                     f'<td class="{e(c.get("direction") or "")}">{e(str(c["to"]))}</td>'
                     + (f'<td>{e(c.get("why") or "")}</td><td class="dim">{e(cost)}</td>' if extra else "") + "</tr>")
        h.append("</table></div>")

    left = [f for f in (after if has else before).get("findings", []) if f.get("severity") != "good"]
    if left:
        h.append("<h3>Still worth knowing</h3><ul>")
        for f in left:
            pre = "This tool does not change this, so it is still true: " if f.get("untouched") else ""
            h.append(f"<li>{e(pre + f['text'])}</li>")
        h.append("</ul>")

    costs = rep.get("costs") or []
    if costs:
        h.append('<h3>What each setting costs on this PC (measured)</h3><div class="scroll"><table>'
                 "<tr><th>Setting</th><th>Compared</th><th>Frame rate it costs</th></tr>")
        for c in costs:
            pct = c["cost_pct"]
            txt = "Almost nothing" if abs(pct) < 0.5 else f"About {pct:.1f}%"
            h.append(f'<tr><td>{e(c["label"])}</td><td>{e(c["level"])} instead of {e(c["lowest"])}</td><td>{txt}</td></tr>')
        h.append("</table></div>")

    shots = rep.get("shots") or []
    if shots:
        h.append("<h3>The same moment, before and recommended</h3>" if has else "<h3>Screenshots from the test</h3>")
        for s in shots:
            name = SCENE_LABELS.get(s.get("scene"), str(s.get("scene")))
            figs = [f'<figure><a href="{e(img(s[k]))}" target="_blank"><img loading="lazy" src="{e(img(s[k]))}" '
                    f'alt="{e(name)} {cap.lower()}"></a><figcaption>{e(name)} &ndash; {cap}</figcaption></figure>'
                    for k, cap in (("before", "Before" if has else "Your settings"), ("after", "Recommended")) if s.get(k)]
            h.append(f'<div class="shots">{"".join(figs)}</div>')
    h.append("</div>")
    return "".join(h)


def page(rep: dict) -> str:
    """Self-contained report page; screenshots are files in the same folder."""
    hw = "".join(f"<tr><td class='dim'>{e(str(r['label']))}</td><td>{e(str(r['value']))}</td></tr>"
                 for r in rep.get("hardware") or [])
    m = rep.get("machine") or {}
    pc = (f"<h3>This PC for DCS: {_grade(m)}</h3><div class='scroll'><table>{hw}</table></div>") if hw and m else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>DCS Graphics Optimizer report</title>
<style>{CSS}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.5 "Segoe UI",system-ui,sans-serif; }}
main {{ max-width:920px; margin:0 auto; padding:24px 16px 40px; }}
h1 {{ font-size:22px; margin:0 0 14px; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:18px; }}
footer {{ color:var(--dim); font-size:13px; margin-top:16px; }}
</style></head><body><main>
<h1>DCS Graphics Optimizer &ndash; test report</h1>
<div class="card">{fragment(rep)}<div class="rep">{pc}</div></div>
<footer>Frame rates were measured on this PC in three fixed scenes on the Caucasus map (a city pass, an airfield
ramp and a cloud layer). Other maps, missions and multiplayer servers will run differently.
Made by DCS Graphics Optimizer; nothing in this report was sent anywhere.</footer>
</main></body></html>
"""
