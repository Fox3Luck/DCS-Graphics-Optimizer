"""Turns a test report (the dict Engine.optimize saves) into HTML: a fragment shown in
the window and a self-contained page saved beside the screenshots for the player to
keep or share. One renderer, so the window and the saved report always agree."""
from __future__ import annotations

from html import escape as e

from .i18n import lang, tr as _

SCENE_LABELS = {"city": "City pass", "airfield": "Airfield ramp", "clouds": "Cloud layer"}

# Shared by the window and the saved page. A and B must not look the same.
# Cockpit/HUD palette: dark panel, amber for attention, HUD green for good. The light scheme is
# for printing and for players whose Windows is in light mode; it keeps the same meanings.
MARK = (
    # A HUD gunsight with a rising frame-rate trace inside it. build/icon.svg is the same
    # mark on a tile, for the Windows icon; keep the two in step.
    '<svg viewBox="0 0 64 64" width="34" height="34" role="img" aria-label="DCS Graphics Optimizer">'
    '<circle cx="32" cy="32" r="19" fill="none" stroke="var(--accent)" stroke-width="3.8"/>'
    '<path d="M32 6v7.5M32 50.5v7.5M6 32h7.5M50.5 32h7.5" stroke="var(--accent)" stroke-width="3.8"'
    ' stroke-linecap="round"/>'
    '<path d="M22 38.5l7.5-7.5 5.5 4.5 9-11.5" fill="none" stroke="var(--good)" stroke-width="5.6"'
    ' stroke-linejoin="round" stroke-linecap="round"/></svg>'
)

# The window always uses DARK (a cockpit at night); the saved report follows the reader's
# system so that it also prints. ui.py appends DARK after CSS to pin the window to it.
DARK = """
:root { --bg:#0b100e; --panel:#121a17; --panel-2:#0e1512; --line:#1f2d28; --line-hi:#2d403a;
        --text:#dce8e2; --dim:#7f948b; --accent:#ffb224; --accent-soft:rgba(255,178,36,.12);
        --good:#3fd98b; --ok:#b7d14a; --warn:#ffb224; --bad:#ff5f56; --on-grade:#0b1210;
        --mono:"Cascadia Mono",Consolas,ui-monospace,monospace; }
"""

CSS = DARK + """
@media (prefers-color-scheme: light) {
  :root { --bg:#f1f4f2; --panel:#fff; --panel-2:#f7faf8; --line:#d8e2dd; --line-hi:#bccac4;
          --text:#13201b; --dim:#55685f; --accent:#8a5a00; --accent-soft:rgba(138,90,0,.10);
          --good:#13784a; --ok:#5a7610; --warn:#8a5a00; --bad:#b32d25; --on-grade:#fff; } }
.letter { width:56px; height:56px; border-radius:10px; display:inline-grid; place-items:center;
          font:700 30px/1 var(--mono); color:var(--on-grade); }
.letter.sm { width:30px; height:30px; font-size:17px; border-radius:6px; vertical-align:middle; margin-right:8px; }
.A { background:var(--good); } .B { background:var(--ok); } .C { background:var(--warn); } .D,.F { background:var(--bad); }
.rep table { width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }
.rep td, .rep th { text-align:left; padding:8px; border-bottom:1px solid var(--line); vertical-align:top; }
.rep th { color:var(--dim); font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:.07em; }
.rep tr:last-child td { border-bottom:0; }
.rep .up { color:var(--good); font-weight:600; } .rep .down { color:var(--warn); font-weight:600; }
.rep .dim { color:var(--dim); } .rep .big { font:700 22px/1.3 var(--mono); margin:0 0 6px; }
.rep .meta { color:var(--dim); margin:0 0 4px; font-size:13px; }
.rep h3 { font-size:12px; margin:24px 0 8px; color:var(--dim); font-weight:600;
          text-transform:uppercase; letter-spacing:.09em; }
.rep .note { border-left:3px solid var(--accent); padding:9px 12px; margin:10px 0;
             background:var(--accent-soft); border-radius:0 6px 6px 0; }
.rep .note.err { border-color:var(--bad); background:var(--panel-2); }
.rep .scroll { overflow-x:auto; }
.rep .shots { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:12px; }
.rep .shots figure { margin:0; } .rep .shots img { width:100%; border-radius:6px; display:block; border:1px solid var(--line); }
.rep .shots figcaption { font-size:13px; color:var(--dim); padding-top:4px; }
.rep .bars { display:grid; gap:10px; margin:14px 0 6px; padding:12px; background:var(--panel-2);
             border:1px solid var(--line); border-radius:8px; font-variant-numeric:tabular-nums; }
.rep .bar-row { display:grid; gap:4px; font-size:13px; }
.rep .bar-head { display:flex; justify-content:space-between; color:var(--dim); font-weight:600; }
.rep .bar-pair { display:grid; grid-template-columns:92px 1fr 68px; gap:8px; align-items:center; font-size:12px; }
.rep .bar-track { position:relative; height:10px; background:var(--bg); border:1px solid var(--line-hi); border-radius:4px; overflow:hidden; }
.rep .bar-track::after { content:""; position:absolute; inset:0; pointer-events:none;
                         background:repeating-linear-gradient(90deg, transparent 0, transparent calc(10% - 1px), rgba(220,232,226,.22) calc(10% - 1px), rgba(220,232,226,.22) 10%); }
.rep .bar-fill { height:100%; border-radius:2px; background:var(--dim); border-right:2px solid #fff; }
.rep .bar-fill.rec { background:linear-gradient(90deg, rgba(63,217,139,.4), var(--good)); }
.rep ul { margin:0; padding-left:18px; } .rep li { padding:3px 0; }
@media (max-width:560px) { .rep .shots { grid-template-columns:1fr; } }
"""


FOOTER = ("Frame rates were measured on this PC in three fixed scenes on the Caucasus map (a city pass, an airfield "
          "ramp and a cloud layer). Other maps, missions and multiplayer servers will run differently. "
          "Made by DCS Graphics Optimizer; nothing in this report was sent anywhere.")


def gb(mb) -> str:
    return f"{mb / 1024:.1f} GB" if mb else _("not measured")


def cost_text(row: dict) -> str:
    pct = row.get("cost_pct")
    if pct is None:
        return ""
    basis = "measured" if row.get("cost_basis") == "measured" else "estimate"
    if abs(pct) < 0.5:
        return _(f"Almost nothing ({basis})")
    word = "of frame rate" if pct > 0 else "frame rate gained"
    return _(f"About {abs(pct):.0f}% {word} ({basis})" if abs(pct) >= 10 else f"About {abs(pct):.1f}% {word} ({basis})")


def _grade(card: dict | None) -> str:
    if not card:
        return ""
    return f'<span class="letter sm {e(card["grade"])}">{e(card["grade"])}</span>{card["score"]} / 100'


def _fps(v) -> str:
    return f"{v:.0f} FPS" if v else _("not measured")


def _meta(rep: dict) -> str:
    bits = []
    if rep.get("kind"):
        bits.append(rep["kind"])
    if rep.get("created"):
        bits.append(rep["created"])
    if rep.get("duration_min"):
        bits.append(f'{rep["duration_min"]} minutes')
    if rep.get("runs"):
        bits.append(f'DCS started {rep["runs"]} times')
    return " &middot; ".join(e(_(str(b))) for b in bits)


def fragment(rep: dict, img=lambda name: name) -> str:
    """The test result. img(name) -> URL for a screenshot file of this report."""
    before, after = rep.get("before") or {}, rep.get("after")
    br, ar = rep.get("before_result") or {}, rep.get("after_result") or {}
    has = bool(after and rep.get("changes"))
    ob, oa = rep.get("overall_before"), rep.get("overall_after")
    h = ['<div class="rep">']
    if has and ob and oa:
        h.append(f'<p class="big">{_("Overall")} {e(ob["grade"])} ({ob["score"]}) &rarr; {e(oa["grade"])} ({oa["score"]})</p>')
    elif has:
        h.append(f'<p class="big">{_("Grade")} {e(before.get("grade", "?"))} &rarr; {e(after["grade"])}</p>')
    else:
        h.append(f'<p class="big">{_("Your settings are already the best match.")}</p>')
    if _meta(rep):
        h.append(f'<p class="meta">{_meta(rep)}</p>')
    if rep.get("target_fps"):
        goal = (f'Goal: hold {rep["target_fps"]} FPS in the worst moments'
                + (f' ({rep["mode_label"]})' if rep.get("mode_label") else '') + '.')
        h.append(f'<p class="meta">{e(_(goal))}</p>')
    if rep.get("applied"):
        h.append('<p class="note">' + e(_(f'These settings were applied on {rep["applied"]}. '
                                          'Use Undo in the app to go back.')) + '</p>')
    if rep.get("vr_skipped"):
        h.append('<p class="note">' + _('VR is switched on in this DCS profile. This test ran on the monitor, so the '
                 'numbers below are monitor numbers, and no VR setting is changed. DCS uses the same graphics '
                 'settings in the headset, so applying these can make VR slower; the tool asks before it does.') + '</p>')
    if rep.get("vr"):
        h.append(f'<p class="note">{_("Measured in the VR headset.")}</p>')
    if rep.get("disturbed"):
        h.append('<p class="note err">' + _('Another program was using the PC during part of this test, so some '
                 'measurements were discarded. For the most accurate result, close other programs and run it again.') + '</p>')
    if rep.get("vram_other_mb"):
        h.append('<p class="note err">' + _(f'Other programs were using {rep["vram_other_mb"] / 1024:.1f} GB of video memory '
                 'before DCS started. The video memory figures below include them, and the recommendation may be '
                 'more cautious than needed. For the most accurate result, close them and run the test again.') + '</p>')
    if has and rep.get("target_reached") is False:
        h.append('<p class="note">' + _(f'This PC cannot hold {rep["target_fps"]} FPS in the heaviest scene; '
                 'this is the smoothest result measured.') + '</p>')

    cols = [("Before" if has else "Your settings", before, br, ob)] + ([("Recommended", after, ar, oa)] if has else [])
    rows = [
        ("Settings grade", lambda c, r, o: _grade(c)),
        ("Overall score", lambda c, r, o: _grade(o)),
        ("Worst moments (1% low)", lambda c, r, o: _fps(r.get("p1_low_fps"))),
        ("Average frame rate", lambda c, r, o: _fps(r.get("avg_fps"))),
        ("Video memory at peak", lambda c, r, o: gb(r.get("vram_peak_mb"))),
        ("Image quality", lambda c, r, o: _(f'{c["quality_share"] * 100:.0f}% of maximum') if c.get("quality_share") is not None else ""),
        ("Upscaling and anti-aliasing", lambda c, r, o: e(_(str(c.get("aa") or "")))),
    ]
    h.append(f'<h3>{_("Measured in DCS")}</h3><div class="scroll"><table><tr><th></th>'
             + "".join(f"<th>{_(col[0])}</th>" for col in cols) + "</tr>")
    for label, fn in rows:
        cells = [fn(c, r, o) for _name, c, r, o in cols]
        if any(cells):
            h.append(f"<tr><td>{_(label)}</td>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    h.append("</table></div>")
    if has:
        bar_items = []
        if br.get("p1_low_fps") and ar.get("p1_low_fps"):
            top = max(float(br["p1_low_fps"]), float(ar["p1_low_fps"]), float(rep.get("target_fps") or 60), 1.0)
            bar_items.append((_("Worst moments (1% low)"), float(br["p1_low_fps"]) / top * 100, _fps(br["p1_low_fps"]),
                              float(ar["p1_low_fps"]) / top * 100, _fps(ar["p1_low_fps"])))
        if br.get("avg_fps") and ar.get("avg_fps"):
            top = max(float(br["avg_fps"]), float(ar["avg_fps"]), 1.0)
            bar_items.append((_("Average frame rate"), float(br["avg_fps"]) / top * 100, _fps(br["avg_fps"]),
                              float(ar["avg_fps"]) / top * 100, _fps(ar["avg_fps"])))
        if before.get("quality_share") is not None and after.get("quality_share") is not None:
            bq, aq = before["quality_share"] * 100, after["quality_share"] * 100
            bar_items.append((_("Image quality"), bq, f"{bq:.0f}%", aq, f"{aq:.0f}%"))
        if bar_items:
            h.append('<div class="bars">')
            for title, bpct, btxt, apct, atxt in bar_items:
                h.append(f'<div class="bar-row"><div class="bar-head"><span>{e(title)}</span></div>'
                         f'<div class="bar-pair"><span class="dim">{e(_("Before"))}</span>'
                         f'<div class="bar-track"><div class="bar-fill" style="width:{min(100, max(2, bpct)):.0f}%"></div></div>'
                         f'<span class="dim">{e(btxt)}</span></div>'
                         f'<div class="bar-pair"><span>{e(_("Recommended"))}</span>'
                         f'<div class="bar-track"><div class="bar-fill rec" style="width:{min(100, max(2, apct)):.0f}%"></div></div>'
                         f'<span class="up">{e(atxt)}</span></div></div>')
            h.append("</div>")

    changes = rep.get("change_list") or []
    if has and changes:
        extra = any("cost_pct" in c or c.get("why") for c in changes)
        h.append(f'<h3>{_("What changes, and what it costs on this PC")}</h3><div class="scroll"><table><tr><th>{_("Setting")}</th>'
                 f'<th>{_("Now")}</th><th>{_("Recommended")}</th>'
                 + (f'<th>{_("What you get")}</th><th>{_("Cost on this PC")}</th>' if extra else "") + "</tr>")
        for c in changes:
            h.append(f'<tr><td>{e(_(str(c["label"])))}</td><td>{e(_(str(c["from"])))}</td>'
                     f'<td class="{e(c.get("direction") or "")}">{e(_(str(c["to"])))}</td>'
                     + (f'<td>{e(_(c.get("why") or ""))}</td><td class="dim">{e(cost_text(c))}</td>' if extra else "") + "</tr>")
        h.append("</table></div>")

    left = [f for f in (after if has else before).get("findings", []) if f.get("severity") != "good"]
    if left:
        h.append(f'<h3>{_("Still worth knowing")}</h3><ul>')
        for f in left:
            pre = _("This tool does not change this, so it is still true: ") if f.get("untouched") else ""
            h.append(f"<li>{e(pre + _(f['text']))}</li>")
        h.append("</ul>")

    costs = rep.get("costs") or []
    if costs:
        h.append(f'<h3>{_("What each setting costs on this PC (measured)")}</h3><div class="scroll"><table>'
                 f'<tr><th>{_("Setting")}</th><th>{_("Compared")}</th><th>{_("Frame rate it costs")}</th></tr>')
        for c in costs:
            pct = c["cost_pct"]
            txt = _("Almost nothing" if abs(pct) < 0.5 else f"About {pct:.1f}%")
            h.append(f'<tr><td>{e(_(c["label"]))}</td><td>{e(_(c["level"] + " instead of " + c["lowest"]))}</td><td>{txt}</td></tr>')
        h.append("</table></div>")

    shots = rep.get("shots") or []
    if shots:
        h.append(f'<h3>{_("The same moment, before and recommended" if has else "Screenshots from the test")}</h3>')
        for s in shots:
            name = _(SCENE_LABELS.get(s.get("scene"), str(s.get("scene"))))
            figs = [f'<figure><a href="{e(img(s[k]))}" target="_blank"><img loading="lazy" src="{e(img(s[k]))}" '
                    f'alt="{e(name)} {cap.lower()}"></a><figcaption>{e(name)} &ndash; {cap}</figcaption></figure>'
                    for k, cap in (("before", _("Before" if has else "Your settings")), ("after", _("Recommended"))) if s.get(k)]
            h.append(f'<div class="shots">{"".join(figs)}</div>')
    h.append("</div>")
    return "".join(h)


def page(rep: dict) -> str:
    """Self-contained report page; screenshots are files in the same folder."""
    hw = "".join(f"<tr><td class='dim'>{e(_(str(r['label'])))}</td><td>{e(_(str(r['value'])))}</td></tr>"
                 for r in rep.get("hardware") or [])
    m = rep.get("machine") or {}
    pc = (f"<h3>{_('This PC for DCS:')} {_grade(m)}</h3><div class='scroll'><table>{hw}</table></div>") if hw and m else ""
    return f"""<!doctype html>
<html lang="{lang()}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_("DCS Graphics Optimizer report")}</title>
<style>{CSS}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.5 "Segoe UI",system-ui,sans-serif; }}
main {{ max-width:920px; margin:0 auto; padding:24px 16px 40px; }}
h1 {{ font-size:19px; margin:0; letter-spacing:.02em; }}
header {{ display:flex; align-items:center; gap:12px; margin:0 0 16px;
          border-bottom:1px solid var(--line); padding-bottom:14px; }}
header svg {{ flex:none; }}
.card {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:18px;
         border-top:2px solid var(--accent); }}
footer {{ color:var(--dim); font-size:13px; margin-top:16px; }}
</style></head><body><main>
<header>{MARK}<h1>{_("DCS Graphics Optimizer &ndash; test report")}</h1></header>
<div class="card">{fragment(rep)}<div class="rep">{pc}</div></div>
<footer>{_(FOOTER)}</footer>
</main></body></html>
"""
