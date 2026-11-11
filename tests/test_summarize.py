"""The summary of received results, fed with what the tool really sends plus hostile rows."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
import summarize as Z

from dcstune import audit, feedback as F
from test_core import INFO
from test_vr import RAW_VR


def _result(rid, gpu="NVIDIA GeForce RTX 4080", low=(100, 121), changes=True, reached=True, vr=None, costs=None,
            disturbed=False, received="2026-11-12T10:00:00Z"):
    info = dict(INFO, gpu=dict(INFO["gpu"], name=gpu), vr=vr or {})
    rep = {"id": rid, "kind": "Thorough test" if costs else "Test and optimize", "target_fps": 120,
           "target_reached": reached, "keep_current": not changes, "disturbed": disturbed, "vr": False,
           "before_result": {"avg_fps": 150, "p1_low_fps": low[0], "scenes": []}}
    if changes:
        rep.update(after_result={"avg_fps": 170, "p1_low_fps": low[1], "scenes": []}, changes={"graphics.shadows": 2})
    if costs:
        rep["costs"] = [{"key": "shadows", "label": "Shadows", "level": "High", "lowest": "Off", "cost_pct": costs}]
    a = audit.build(info, {"graphics.width": 2560, "graphics.height": 1440, "VR.enable": bool(vr)}, rep, {"version": "2.9"})
    return dict(F.payload("result", rid, a), received=received)


def _rows():
    f = lambda rid, ev, **k: dict(F.payload(ev, rid, **k), received="2026-11-12T11:00:00Z")
    return [
        _result("a" * 16, costs=8.0),
        f("a" * 16, "applied"), f("a" * 16, "feedback", feel="better", comment="smooth over Batumi"),
        _result("b" * 16, gpu="Matrox Future 9000", low=(60, 75), reached=False, costs=14.0),
        f("b" * 16, "applied"), f("b" * 16, "undone"), f("b" * 16, "feedback", feel="worse", comment="shimmer\x1b[31m on trees"),
        _result("c" * 16, changes=False, vr=RAW_VR),
        _result("d" * 16, changes=False, vr={"runtime": r"C:\Program Files\Varjo\varjo-openxr\VarjoOpenXR.json",
                                             "layers": [r"C:\x\XR_APILAYER_MBUCCHIA_quad_views_foveated.json"]}),
        _result("e" * 16, costs=99.0, disturbed=True),
        f("f" * 16, "applied"),                                                    # its result never arrived
        dict(F.payload("applied", "0" * 16), tool_version="deploy-check", received="2026-11-11T16:00:00Z"),
    ]


def test_summary_numbers():
    s = Z.summarise(_rows())
    assert s["tests"] == 5 and s["deploy_checks"] == 1 and s["follow_ups_without_result"] == 1
    o = s["outcomes"]
    assert o["with_recommendation"] == 3 and o["applied"] == 2 and o["undone"] == 1 and o["undone_pct"] == 50
    assert o["already_best"] == 2 and o["goal_reached_pct"] == 80 and o["disturbed"] == 1
    assert o["feel"] == {"better": 1, "same": 0, "worse": 1} and o["low_fps_gain_median"] == 21
    gpus = {g["name"]: g for g in s["gpus"]}
    assert gpus["NVIDIA GeForce RTX 4080"]["tests"] == 4 and gpus["NVIDIA GeForce RTX 4080"]["in_table"] is True
    assert gpus["Matrox Future 9000"]["low_fps"] == 60
    v = s["vr"]
    assert v["pcs_with_vr_software"] == 2 and v["headsets"] == {"Pimax Crystal Light": 1}
    assert v["not_recognised"] == [{"runtime_file": "VarjoOpenXR", "runtime": v["not_recognised"][0]["runtime"],
                                    "pimax_models": "-", "layers": "XR_APILAYER_MBUCCHIA_quad_views_foveated", "tests": 1}]
    cost = s["costs"][0]
    assert cost["key"] == "shadows" and cost["tests"] == 2 and cost["median_pct"] == 11.0 and cost["max_pct"] == 14.0   # disturbed test left out
    assert [r["gpu"] for r in s["worse_or_undone"]] == ["Matrox Future 9000"]
    assert [r["gpu"] for r in s["missed_goal"]] == ["Matrox Future 9000"]
    assert len(s["comments"]) == 2


def test_report_text_is_safe_and_readable(tmp_path, capsys):
    f = tmp_path / "feedback-2026-11.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in _rows()) + "\nnot json\n[1,2]\n" + json.dumps({"schema": "x"}) + "\n")
    rows, bad = Z.read([str(tmp_path)])
    assert bad == 3
    text = Z.render(Z.summarise(rows, bad))
    assert "5 tests from 11 submissions" in text and "3 unreadable lines" in text and "1 install-check rows left out" in text
    assert "NO - add it" in text and "Pimax Crystal Light (1)" in text and "VarjoOpenXR" in text
    assert "felt worse | undone" in text and "smooth over Batumi" in text
    assert "\x1b" not in text and "shimmer [31m on trees" in text              # control characters never reach the terminal
    assert "read these as individual cases" in text


def test_hostile_rows_cannot_break_it():
    junk = {"schema": "dcsgo-feedback/1", "id": "9" * 16, "event": "result", "received": 5, "tool_version": ["x"],
            "audit": {"hardware": "nope", "vr": {"detected": [1], "pimax": {"models": "abc"}}, "test": {
                "costs": [{"cost_pct": "NaN"}, 7, {"cost_pct": 3.0}], "changes": [1, 2], "before_result": {"avg_fps": "fast"},
                "target_reached": "yes"}}}
    s = Z.summarise([junk, {"schema": "dcsgo-feedback/1", "id": "8" * 16, "event": "feedback", "feel": {"a": 1}, "comment": 7}])
    assert s["tests"] == 1 and s["outcomes"]["goal_reached_pct"] == 0 and s["gpus"][0]["name"] == "?"
    assert "1 tests" in Z.render(s)
    assert "No test results yet" in Z.render(Z.summarise([]))
