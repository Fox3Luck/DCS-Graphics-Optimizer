# DCS Graphics Optimizer - Fox3 Managed Solutions Inc.
# Created 2026-11-10. The program's window and the engine behind its buttons (local page, this PC only).
"""DCS Graphics Optimizer window. A tiny local web page (127.0.0.1 only, random port, secret token)
shown in a native window via pywebview when installed, otherwise the default browser.

  python -m dcstune.ui
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PAGE = Path(__file__).parent / "ui.html"
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".bmp": "image/bmp"}


class Engine:
    """Everything the window can do. Tests replace this with a fake."""

    def __init__(self, profile_name: str | None = None):
        from . import bench, sysinfo
        from .optionslua import recover
        self.info = sysinfo.collect()
        self.profile = sysinfo.pick_profile(self.info, profile_name)
        self._use_prefs()
        self.recovered = recover(self.profile["options"], keep_player_edits=True)
        if not bench.dcs_running():
            bench.remove_leftovers(self.profile["path"])     # a hook left by an interrupted test

    def _use_prefs(self):
        """What the player picked earlier in this profile: the headset (used when the tool cannot
        tell by itself), the refresh rate they run it at, and their own frame-rate goal."""
        from . import prefs
        self.info["vr"] = dict(self.info.get("vr") or {}, chosen=prefs.get_pref(self.profile, "headset"),
                               hz=prefs.get_pref(self.profile, "headset_hz"),
                               goal=prefs.get_pref(self.profile, "vr_goal"))
        self.info["fps_goal"] = prefs.get_pref(self.profile, "fps_goal")
        self.info["bench_scene"] = prefs.get_pref(self.profile, "bench_scene")
        self.info["bench_busy"] = prefs.get_pref(self.profile, "bench_busy") is True
        self.vr_in_headset = prefs.get_pref(self.profile, "vr_in_headset") is True

    def _vr_bench(self) -> bool:
        """Does the test run inside the headset? Always in a VR test build; in the regular build only
        when the player chose it (issue #10: VR players were sent to a separate build, whose update
        notice then pointed them back at a build that tests on the monitor, #42)."""
        from . import vr as V
        return V.bench_enabled() or getattr(self, "vr_in_headset", False)

    def set_vr_test(self, in_headset) -> str:
        """Where a VR profile is tested: in the headset (True) or on the monitor (anything else)."""
        from . import prefs
        prefs.set_pref(self.profile, "vr_in_headset", in_headset is True)
        self._use_prefs()
        if getattr(self, "vr_in_headset", False):
            return ("The test will run in your headset. Connect it and open its software before you start, "
                    "and wear it or keep it awake during the test. This is still being tested with VR "
                    "volunteers; please tell us how it goes.")
        return "The test will run on the monitor, and your VR settings are left alone."

    def set_headset(self, name) -> str:
        from . import prefs, vr as V
        name = name if name in V.headset_names() else None
        prefs.set_pref(self.profile, "headset", name)
        self._use_prefs()
        return (f"Headset set to {name}. The scorecard is now rated for it." if name
                else "Headset cleared. The scorecard assumes a typical headset.")

    def set_headset_hz(self, hz) -> str:
        """The refresh rate the player runs the headset at; None goes back to the usual one."""
        from . import prefs, vr as V
        st = V.state(self.info, self._flat())
        rates = st["refresh"] if st else []
        hz = hz if isinstance(hz, int) and not isinstance(hz, bool) and hz in rates else None
        prefs.set_pref(self.profile, "headset_hz", hz)
        self._use_prefs()
        st = V.state(self.info, self._flat())
        aim = st["target"] if st else hz
        return (f"Headset refresh rate set to {hz} Hz. The scorecard and the test now aim for {aim} FPS." if hz
                else "Headset refresh rate set back to automatic.")

    def set_vr_goal(self, mode) -> str:
        """The player's own goal in the headset (#47): half rate for motion smoothing, with or without
        room to spare; None goes back to the headset's full refresh rate."""
        from . import prefs, vr as V
        mode = mode if isinstance(mode, str) and mode in V.GOAL_MODES else None
        if not V.state(self.info, self._flat()):
            return "VR is switched off in this profile, so there is no headset goal to set."
        prefs.set_pref(self.profile, "vr_goal", mode)
        self._use_prefs()
        st = V.state(self.info, self._flat())
        if not mode:
            return f"Headset goal set back to the full refresh rate: {st['target']} FPS."
        return (f"Headset goal set to {st['target']} FPS, for flying with motion smoothing at {st['hz']} Hz. "
                "The scorecard and the test now aim for it.")

    def _install_root(self):
        from . import sysinfo
        try:
            return sysinfo.pick_install(self.info).get("path")
        except Exception:
            return None

    def heat_check(self, log=print) -> dict:
        """Fly the test scenes over and over with the player's own settings and say whether the
        frame rate falls as the PC warms up (#23). Changes no settings and recommends none."""
        from . import heat, scenes, sysinfo, vr as V
        from .bench import Bench
        flat, gpu = self._flat(), self.info["gpu"]
        st = V.state(self.info, flat)
        in_headset = bool(st) and self._vr_bench()
        exe = sysinfo.dcs_exe(sysinfo.pick_install(self.info))
        scene = scenes.valid(self.info.get("bench_scene"))
        if scene and not any(m["key"] == scene[0] for m in scenes.installed(self._install_root(), self.profile["path"])["maps"]):
            scene = None
        busy = self.info.get("bench_busy") is True and scenes.busy_ok(scene)
        log("Heat check: the same scenes six times in a row with your current settings, about 15 minutes. "
            "Nothing is changed.")
        log("Scenes: " + scenes.label(scene) + (", with the busy airfield scene" if busy else "") + ".")
        from . import rate
        from .bench import fps_cap
        goal = (st["target"] if in_headset else None) or rate.chosen_goal(self.info) or rate.display_goal(self.info)
        cap = fps_cap(goal)
        log(f"Frame rate limited to {cap} FPS during the check (twice your goal of {goal:.0f}), so the graphics "
            "card is not driven harder than it needs to be.")
        with Bench(self.profile, exe, log=log, vr=in_headset, vram_total_mb=gpu.get("vram_mb") or 0, scene=scene,
                   busy=busy) as b:
            b.fps_cap = cap
            raw = b.soak()
        out = heat.summarize(raw["laps"], raw["samples"], cap)
        out["created"] = time.strftime("%Y-%m-%d %H:%M")
        out["scene_label"] = scenes.label(scene) + (", with the busy airfield scene" if busy else "")
        for line in out["lines"]:
            log(line)
        return out

    def set_busy(self, on) -> str:
        """Add the busy-airfield scene to the test, or take it out (issues #23, #35)."""
        from . import prefs, scenes
        on = on is True
        if on and not scenes.busy_ok(self.info.get("bench_scene")):
            raise ValueError("There is no busy scene for this map and aircraft yet.")
        prefs.set_pref(self.profile, "bench_busy", on)
        self._use_prefs()
        if on:
            return ("The test now adds a fourth scene: a busy airfield with about 150 moving vehicles, aircraft, "
                    "helicopters and fires. Each run takes about half a minute longer. Don't expect it to change "
                    "what the tool recommends: on our test PC the graphics card still set the frame rate there, the "
                    "same as in the other scenes. A full multiplayer server is far heavier, with hundreds to "
                    "thousands of units and scripts, which a repeatable test can't copy. Use this scene to see your "
                    "frame rate with more on screen, and the frame-rate goal to leave room for multiplayer.")
        return "The busy airfield scene is off. The test flies the three standard scenes."

    def set_scene(self, map_key, aircraft) -> str:
        """The map and aircraft the test flies (#23); anything not offered goes back to the default."""
        from . import prefs, scenes
        pick = scenes.valid((map_key, aircraft))
        have = scenes.installed(self._install_root(), self.profile["path"])
        if pick and not (any(m["key"] == pick[0] for m in have["maps"])
                         and any(a["key"] == pick[1] for a in have["aircraft"])):
            pick = None
        prefs.set_pref(self.profile, "bench_scene", list(pick) if pick else None)
        self._use_prefs()
        if not pick:
            return "The test is back on the standard scenes: " + scenes.label(None) + "."
        return ("The test now flies " + scenes.label(pick) + ". Results from different maps or aircraft "
                "can't be compared with each other; a heavier pair gives lower numbers.")

    def set_goal(self, fps) -> str:
        """The player's own frame-rate goal for monitor tests; None goes back to automatic."""
        from . import prefs, rate
        fps = fps if isinstance(fps, int) and not isinstance(fps, bool) and fps in rate.GOAL_CHOICES else None
        prefs.set_pref(self.profile, "fps_goal", fps)
        self._use_prefs()
        return (f"Frame-rate goal set to {fps} FPS. The scorecard and the test now aim for it." if fps
                else "Frame-rate goal set back to automatic (your monitor's refresh rate).")

    def _flat(self):
        from . import rate
        from .optionslua import Options
        return rate.flat_options(Options.load(self.profile["options"]))

    def report_path(self) -> Path:
        return Path(self.profile["path"]) / "Config" / "dcstune-report.json"

    def reports_dir(self) -> Path:
        """Where saved reports (a page plus its screenshots) are kept for the player."""
        return Path(self.profile["path"]) / "DCS Graphics Optimizer Reports"

    def _report(self) -> dict | None:
        rp = self.report_path()
        try:
            return json.loads(rp.read_text()) if rp.exists() else None
        except ValueError:
            return None

    def report_file(self, name: str) -> Path | None:
        """A file of the current saved report (page or screenshot), or None. Names only:
        the window must not be able to read anything else on the PC through this."""
        rep = self._report() or {}
        if not rep.get("dir") or name != Path(name).name or Path(name).suffix.lower() not in IMAGE_TYPES:
            return None
        f = self.reports_dir() / Path(rep["dir"]).name / name
        return f if f.is_file() else None

    def open_report(self) -> str:
        rep = self._report() or {}
        page = self.reports_dir() / Path(rep.get("dir") or "-").name / "report.html"
        if not page.is_file():
            raise RuntimeError("There is no saved report yet. Run a test first.")
        if hasattr(os, "startfile"):
            os.startfile(page)          # the player's own browser
        else:
            webbrowser.open(page.as_uri())
        return f"Opened {page}"

    def _save_report_folder(self, report: dict, out: dict) -> None:
        """Move the before/recommended screenshots out of DCS's ScreenShots folder into a
        dated report folder and write the report page beside them."""
        from . import report as R
        from .optionslua import atomic_write
        folder = self.reports_dir() / ("report-" + time.strftime("%Y%m%d-%H%M%S"))
        folder.mkdir(parents=True, exist_ok=True)
        shots_dir = Path(self.profile["path"]) / "ScreenShots"

        def take(stem):
            for src in sorted(shots_dir.glob(stem + ".*")) if stem else []:
                if src.suffix.lower() in IMAGE_TYPES:
                    dst = folder / src.name
                    try:
                        src.replace(dst)
                    except OSError:
                        continue
                    return dst.name
            return None

        def by_scene(res):
            return {s.get("name"): s.get("shot") for s in ((res or {}).get("raw") or res or {}).get("scenes", [])}
        before, after = by_scene(out["before"]), by_scene((out["recommended"] or {}).get("result"))
        shots = []
        for scene in before:
            row = {"scene": scene, "before": take(before.get(scene)), "after": take(after.get(scene))}
            if row["before"] or row["after"]:
                shots.append(row)
        report.update(dir=folder.name, shots=shots)
        atomic_write(folder / "report.html", R.page(report).encode("utf-8"))
        try:      # what the tool saw and measured, for the player to send back if they choose to
            from . import audit, sysinfo
            atomic_write(folder / "audit.json",
                         audit.text(self.info, self._flat_at_test, report, sysinfo.pick_install(self.info)).encode("utf-8"))
        except Exception:      # the audit file must never cost the player their report
            pass

    def scorecard(self) -> dict:
        from . import rate
        from .optionslua import list_backups
        machine = rate.rate_machine(self.info)
        flat = self._flat()
        fit = rate.rate_settings(self.info, flat, machine,
                                 calibration=rate.load_calibration(self.profile, self.info, flat))
        from . import vr as V
        st = V.state(self.info, flat)
        return {"profile": self.profile["name"], "profile_dir": Path(self.profile["path"]).name,
                "vr_tested": bool(st) and self._vr_bench(), "vr_test_build": V.test_build(),
                "vr_choice": bool(st) and not V.bench_enabled(),      # the regular build lets the player choose
                "headset": st and {"name": st["headset"], "detected": st["detected"],
                                   "choices": V.headset_names(), "refresh": st["refresh"],
                                   "hz": st["hz"], "hz_chosen": st["hz_chosen"],
                                   "goal_mode": st["goal_mode"] or "", "goal_fps": st["target"],
                                   "goal_choices": V.goal_choices(st["hz"])},
                "scene": self._scene_card(),
                "goal": {"chosen": rate.chosen_goal(self.info), "choices": list(rate.GOAL_CHOICES),
                         "auto": rate.target_fps((self.info.get("gpu") or {}).get("refresh"))},
                "hardware": rate.hardware_summary(self.info, flat), "overall": rate.overall(machine, fit),
                "profile_path": self.profile["path"],
                "profiles": [{"name": p.get("name"), "path": p.get("path")} for p in self.info["profiles"]],
                "machine": machine,
                "settings": fit,
                "vr": bool(flat.get("VR.enable")), "recovered": self.recovered,
                "can_undo": bool(list_backups(self.profile["options"])),
                "report": self._report()}

    def _scene_card(self) -> dict:
        from . import scenes
        have = scenes.installed(self._install_root(), self.profile["path"])
        pick = scenes.valid(self.info.get("bench_scene")) or scenes.DEFAULT
        if not any(m["key"] == pick[0] for m in have["maps"]):      # the map was removed or switched off since
            pick = scenes.DEFAULT
        combos = {k: m["aircraft"] for k, m in scenes.index()["maps"].items()}
        return {"busy": self.info.get("bench_busy") is True and scenes.busy_ok(pick), "busy_ok": scenes.busy_ok(pick),
                "map": pick[0], "aircraft": pick[1], "label": scenes.label(pick),
                "default": pick == scenes.DEFAULT, "maps": have["maps"], "aircraft_list": have["aircraft"],
                "combos": combos}

    def optimize(self, full: bool, log, mode: str = "balanced") -> dict:
        from . import audit, model as M, optimize, rate, sysinfo, vr as V
        from .bench import Bench, other_vram_high
        from .optionslua import atomic_write
        started = time.time()
        flat, gpu = self._flat(), self.info["gpu"]
        self._flat_at_test = dict(flat)       # the player's real settings, for the audit file
        st = V.state(self.info, flat)
        vr_skipped = bool(st) and not self._vr_bench()
        if vr_skipped:
            # Measuring inside the headset is not released yet: test on the monitor, rate the
            # result as a monitor result, and leave every VR setting alone.
            log("VR is switched on in this profile. This test runs on the monitor and your VR settings are left alone.")
            flat, st = dict(flat, **{"VR.enable": False}), None
        machine = rate.rate_machine(self.info)
        vendor = sysinfo.upscaling_vendor(self.info, flat)
        if vendor != sysinfo.gpu_vendor(self.info):
            log("DLSS is selected on a card that is not NVIDIA (through OptiScaler, for example), so DLSS choices are kept on offer.")
        mdl = M.Model(machine["gpu_score"], machine["cpu_score"],
                      flat.get("graphics.width") or gpu["width"], flat.get("graphics.height") or gpu["height"], vendor,
                      vr=st and st["model"])
        goal = st["target"] if st else rate.display_goal(self.info)
        own_goal = (st["target"] if st["hz_chosen"] or st["goal_mode"] else None) if st else rate.chosen_goal(self.info)
        if own_goal:
            log(f"Your own goal: {own_goal} FPS"
                + (f" (for flying with motion smoothing at {st['hz']} Hz)." if st and st["goal_mode"]
                   else " (the refresh rate you picked for your headset)." if st else "."))
        extra = V.fixed_changes(st, flat) if st else None
        if extra and "VR.pixel_density" in extra:      # candidates are judged at the density they will use
            mdl.vr = dict(mdl.vr, pd=extra["VR.pixel_density"])
        # Reuse what an earlier thorough test measured on this PC (same card, processor and
        # resolution); a thorough test re-measures and overwrites it.
        cal = rate.load_calibration(self.profile, self.info, flat)
        if cal and not full:
            mdl.measured = {k: {int(i): ms for i, ms in v.items()} for k, v in cal.get("measured", {}).items()}
        exe = sysinfo.dcs_exe(sysinfo.pick_install(self.info))
        from . import scenes
        scene = scenes.valid(self.info.get("bench_scene"))
        if scene and not any(m["key"] == scene[0] for m in scenes.installed(self._install_root(), self.profile["path"])["maps"]):
            log("The map you picked for the test is not installed or is switched off in DCS's module manager; "
                "using the standard scenes.")
            scene = None
        if scene:
            log("Test scenes: " + scenes.label(scene) + " (your own choice).")
        busy = self.info.get("bench_busy") is True and scenes.busy_ok(scene)
        if busy:
            log("With the busy airfield scene (your own choice).")
        from .bench import fps_cap
        cap = fps_cap(own_goal or goal)
        log(f"The test runs with the frame rate limited to {cap} FPS (twice your goal), so the graphics card is "
            "not driven harder than it needs to be.")
        with Bench(self.profile, exe, log=log, vr=bool(st), vram_total_mb=gpu.get("vram_mb") or 0, scene=scene,
                   busy=busy) as b:
            b.fps_cap = cap
            out = optimize.run(mdl, flat, vendor, goal,
                               gpu.get("vram_mb") or 0, b.measure, full=full, log=log,
                               measure_fast=b.measure_fast, measure_batch=b.measure_batch,
                               steps=st and st["steps"], extra=extra, mode=mode, fps_cap=cap)
            launches, other_vram = b.runs, b.other_vram_mb
            for res in (out["before"], (out["recommended"] or {}).get("result") or {}):
                b.keep_shots.update(s["shot"] for s in (res.get("raw") or {}).get("scenes", []) if s.get("shot"))
        target = out["target_fps"]
        rate.save_calibration(self.profile, self.info, flat, out["learned"],
                              [(flat, out["before"])] + [(dict(flat, **h["changes"]), h["result"]) for h in out["history"]])
        base_ms = 1000.0 / out["before"]["avg_fps"]
        report = {"id": secrets.token_hex(8),       # random, per test; lets a later Apply or comment refer to it
                  "created": time.strftime("%Y-%m-%d %H:%M"), "profile": self.profile["name"],
                  "kind": "Thorough test" if full else "Test and optimize",
                  "mode": mode, "mode_label": optimize.MODES[mode]["label"],
                  "duration_min": max(1, round((time.time() - started) / 60)),
                  "hardware": rate.hardware_summary(self.info, flat),
                  "vr": bool(st), "vr_skipped": vr_skipped,
                  "scene": list(scene) if scene else None, "scene_label": scenes.label(scene), "busy": busy,
                  "costs": optimize.measured_costs(mdl, base_ms),
                  "target_fps": target, "goal_chosen": own_goal, "target_reached": out["target_reached"],
                  "keep_current": out["keep_current"], "runs": launches,
                  "disturbed": out["disturbed"],
                  "before": rate.rate_settings(self.info, flat, machine, out["before"], target),
                  "machine": machine,
                  "before_result": _slim(out["before"])}
        if other_vram_high(other_vram, gpu.get("vram_mb") or 0, vr=bool(st)):
            report["vram_other_mb"] = round(other_vram)       # shown as a note on the report
        rec = out["recommended"]
        if rec:
            after = dict(flat)
            after.update(rec["changes"])
            report.update(after=rate.rate_settings(self.info, after, machine, rec["result"], target),
                          overall_after=None,
                          after_result=_slim(rec["result"]), changes=rec["changes"],
                          change_list=optimize.describe_changes(flat, rec["changes"], vendor, mdl, base_ms))
        report["overall_before"] = rate.overall(machine, report["before"])
        if "after" in report:
            report["overall_after"] = rate.overall(machine, report["after"])
        try:
            self._save_report_folder(report, out)
        except OSError as e:
            log(f"The report page could not be saved ({e}); the result is still shown here.")
        atomic_write(self.report_path(), json.dumps(report, indent=1).encode())
        return report

    VR_WARNING = ("[vr] VR is switched on in this DCS profile, but this test ran on the monitor. DCS uses the same "
                  "graphics settings in the headset, so settings that are smooth on the monitor can be much slower in "
                  "VR (players have seen their headset frame rate halve). Apply them anyway?")

    def apply(self, vr_ok: bool = False, skip=()) -> str:
        """Write the recommendation. skip: change-list keys the player unticked (#24); they
        stay as they are. "upscaling" stands for the DCS options behind that one choice."""
        from .bench import dcs_running
        from .optionslua import Options, atomic_write, backup
        if dcs_running():
            raise RuntimeError("Close DCS first. It overwrites its settings file when it exits.")
        rp, rep = self.report_path(), self._report() or {}
        changes = rep.get("changes")
        if not changes:
            raise RuntimeError("There is no recommendation to apply yet.")
        if rep.get("applied"):
            raise RuntimeError("These settings are already applied.")
        from .optimize import RUNG_KEYS
        rows = {c.get("key") for c in rep.get("change_list") or []}
        skip = sorted({str(k) for k in (skip or ()) if str(k) in rows})
        drop = set(skip) | (set(RUNG_KEYS) if "upscaling" in skip else set())
        changes = {k: v for k, v in changes.items() if k not in drop}
        if not changes:
            raise RuntimeError("Everything is unticked, so there is nothing to apply.")
        measured_on_monitor = not rep.get("vr")
        if measured_on_monitor and (rep.get("vr_skipped") or self._flat().get("VR.enable")) and not vr_ok:
            raise RuntimeError(self.VR_WARNING)
        saved = backup(self.profile["options"])
        opts = Options.load(self.profile["options"])
        opts.update(changes)
        opts.save(self.profile["options"])
        rep["applied"] = time.strftime("%Y-%m-%d %H:%M")   # keep the report; the player may want to read it again
        rep["skipped"] = skip
        atomic_write(rp, json.dumps(rep, indent=1).encode())
        if skip:
            return (f"Applied, leaving {len(skip)} setting{'s' if len(skip) > 1 else ''} as you had "
                    f"{'them' if len(skip) > 1 else 'it'}. That mix was not tested as a whole, so your frame rate can "
                    f"differ a little from the report. Your previous settings are kept as {saved.name}.")
        return f"Applied. Your previous settings are kept as {saved.name}."

    def undo(self) -> str:
        from .bench import dcs_running
        from .optionslua import atomic_write, list_backups
        if dcs_running():
            raise RuntimeError("Close DCS first. It overwrites its settings file when it exits.")
        backups = list_backups(self.profile["options"])
        if not backups:
            raise RuntimeError("No earlier settings saved by DCS Graphics Optimizer were found.")
        atomic_write(Path(self.profile["options"]), backups[-1].read_bytes())
        backups[-1].unlink()
        rep = self._report()
        if rep and rep.pop("applied", None):
            rep.pop("skipped", None)
            atomic_write(self.report_path(), json.dumps(rep, indent=1).encode())
        return "Your previous settings are back."


def can_browse() -> bool:
    """A folder picker exists only in the app's own window (pywebview), not in a browser."""
    try:
        import webview
        return bool(webview.windows)
    except ImportError:
        return False


def browse_folder(title: str) -> str | None:
    """Windows' folder picker over the app window; None if canceled or unavailable."""
    if not can_browse():
        return None
    import webview
    kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
    try:
        picked = webview.windows[0].create_file_dialog(kind)
    except Exception:
        return None
    return picked[0] if picked else None


def _slim(summary: dict) -> dict:
    return {k: summary.get(k) for k in ("avg_fps", "p1_low_fps", "vram_peak_mb")} | {
        "scenes": [{k: s.get(k) for k in ("name", "avg_fps", "p1_low_fps", "stutters", "shot", "gpu_busy")}
                   for s in (summary.get("raw") or summary).get("scenes", [])]}



def chime(event: str) -> None:
    """A Windows sound when a test starts and when it ends (VR beta feedback, #30: with the
    headset on, the player cannot see the window). Silent where there is no sound."""
    try:
        import winsound
        winsound.MessageBeep({"start": winsound.MB_OK, "done": winsound.MB_ICONASTERISK,
                              "failed": winsound.MB_ICONHAND}[event])
    except Exception:
        pass

class App:
    """Holds the single background job (optimize) and its progress log."""

    def __init__(self, engine_factory=Engine):
        self.token = secrets.token_urlsafe(16)
        self._factory, self._engine = engine_factory, None
        self.lock = threading.Lock()
        self.job = {"state": "idle", "log": [], "error": None, "report": None}
        self.update = None            # a newer release, once the background check has found one

    def check_for_update(self) -> None:
        """Run once at start, in the background (see updates.py)."""
        from . import updates
        self.update = updates.check()

    @property
    def engine(self):
        if self._engine is None:
            self._engine = self._factory()
        return self._engine

    def start_optimize(self, full: bool, mode: str = "balanced") -> None:
        from .optimize import MODES
        if mode not in MODES:
            raise RuntimeError("Choose Smoothness, Balanced or Quality.")
        with self.lock:
            if self.job["state"] == "running":
                raise RuntimeError("A test is already running.")
            self.job = {"state": "running", "log": [], "error": None, "report": None, "started": time.time()}
        threading.Thread(target=self._work, args=(full, mode), daemon=True).start()

    def start_heat(self) -> None:
        with self.lock:
            if self.job["state"] == "running":
                raise RuntimeError("A test is already running.")
            self.job = {"state": "running", "log": [], "error": None, "report": None, "started": time.time()}
        threading.Thread(target=self._work, args=(None, "heat"), daemon=True).start()

    def _work(self, full, mode="balanced"):
        job = self.job
        chime("start")
        try:
            if mode == "heat":
                job["heat"] = self.engine.heat_check(lambda m: job["log"].append(str(m)))
            else:
                job["report"] = self.engine.optimize(full, lambda m: job["log"].append(str(m)), mode)
            job["state"] = "done"
            chime("done")
        except Exception as e:
            job["error"] = str(e)
            self._failure_log(job)
            job["state"] = "failed"
            chime("failed")

    def _failure_log(self, job: dict) -> None:
        """Attach an anonymized extract of DCS's log to a failed test. Nothing is sent: the
        window shows it so the player can copy it into a GitHub issue or the Discord channel."""
        from . import failurelog, sysinfo
        try:
            eng = self.engine
            try:
                inst = sysinfo.pick_install(eng.info)
            except Exception:
                inst = None
            lines = failurelog.for_profile(eng.profile, inst, since=job.get("started", 0) - 5)
        except Exception:
            return
        if lines:
            job["failure_log"] = {"lines": lines}

    def setup_needed(self) -> dict | None:
        """What the player must point to before anything else works, or None."""
        from .sysinfo import SetupNeeded
        try:
            eng = self.engine
        except SetupNeeded as e:
            return {"what": e.what, "message": str(e)}
        if not (getattr(eng, "info", None) or {}).get("installs", [None]):
            from .sysinfo import pick_install
            try:
                pick_install(eng.info)
            except SetupNeeded as e:
                return {"what": e.what, "message": str(e)}
        return None

    def choose_folder(self, what: str, path: str | None) -> dict:
        """Remember a folder the player typed or picked, then look at the PC again."""
        from . import sysinfo
        if what not in ("install", "profile"):
            raise KeyError(what)
        if not path:
            path = browse_folder("Where is DCS World installed?" if what == "install"
                                 else "Where is your Saved Games\\DCS folder?")
            if not path:
                return {"message": ""}
        msg = sysinfo.choose(what, path)
        with self.lock:
            if self.job["state"] == "running":
                raise RuntimeError("A test is running; change the folder after it finishes.")
            self._engine = None
        return {"message": msg}

    def handle(self, method: str, path: str, body: dict) -> dict:
        if method == "POST" and path == "/api/choose-folder":
            return self.choose_folder(str(body.get("what")), body.get("path"))
        if method == "GET" and path == "/api/scorecard":
            from . import report as R
            setup = self.setup_needed()
            if setup and setup["what"] == "profile":
                return {"setup": setup, "can_browse": can_browse()}
            sc = self.engine.scorecard()
            sc["can_browse"] = can_browse()
            if setup:
                sc["setup"] = setup
            if sc.get("report") and sc["report"].get("before"):
                sc["report_html"] = R.fragment(sc["report"], lambda name: f"/report-file/{name}?t={self.token}",
                                                pick=True)
            return sc
        if method == "GET" and path == "/api/job":
            return self.job
        if method == "POST" and path == "/api/open-link":
            from . import community
            return {"message": community.open_link(str(body.get("which")))}
        if method == "POST" and path == "/api/optimize":
            setup = self.setup_needed()
            if setup:
                raise RuntimeError(setup["message"])
            self.start_optimize(bool(body.get("full")), str(body.get("mode") or "balanced"))
            return {"ok": True}
        if method == "POST" and path == "/api/heat":
            self.start_heat()
            return {"ok": True}
        if method == "POST" and path == "/api/apply":
            skip = body.get("skip")
            return {"message": self.engine.apply(body.get("vr_ok") is True,
                                                 skip if isinstance(skip, list) else ())}
        if method == "POST" and path == "/api/headset":
            with self.lock:
                if self.job["state"] == "running":
                    raise RuntimeError("A test is running; pick the headset after it finishes.")
            return {"message": self.engine.set_headset(body.get("name"))}
        if method == "POST" and path in ("/api/headset-hz", "/api/goal", "/api/vr-goal", "/api/scene", "/api/vr-test", "/api/busy"):
            with self.lock:
                if self.job["state"] == "running":
                    raise RuntimeError("A test is running; change the goal after it finishes.")
            if path == "/api/goal":
                return {"message": self.engine.set_goal(body.get("fps"))}
            if path == "/api/vr-test":
                return {"message": self.engine.set_vr_test(body.get("in_headset"))}
            if path == "/api/busy":
                return {"message": self.engine.set_busy(body.get("on"))}
            if path == "/api/scene":
                return {"message": self.engine.set_scene(body.get("map"), body.get("aircraft"))}
            if path == "/api/vr-goal":
                return {"message": self.engine.set_vr_goal(body.get("mode"))}
            return {"message": self.engine.set_headset_hz(body.get("hz"))}
        if method == "POST" and path == "/api/undo":
            return {"message": self.engine.undo()}
        if method == "GET" and path == "/api/version":
            from . import __version__, vr as V
            return {"version": __version__ + (" (VR test build)" if V.test_build() else ""),
                    "update": self.update}
        if method == "POST" and path == "/api/open-download":
            from . import updates
            url = (self.update or {}).get("url") or updates.RELEASES_PAGE
            if not updates.is_release_page(url):
                raise RuntimeError("Not a download page of this tool.")
            webbrowser.open(url)
            return {"message": "The download page is open in your browser. Close this window before running the new version."}
        if method == "POST" and path == "/api/open-report":
            return {"message": self.engine.open_report()}
        raise KeyError(path)


def make_server(app: App, port: int = 0) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, payload, ctype="application/json"):
            data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _route(self, method):
            path, _, query = self.path.partition("?")
            if method == "GET" and path == "/":
                if query != "t=" + app.token:
                    return self._send(403, {"error": "forbidden"})
                from . import report as R
                html = PAGE.read_bytes().replace(b"__TOKEN__", app.token.encode())
                return self._send(200, html.replace(b"/*__REPORT_CSS__*/", R.CSS.encode()),
                                  "text/html; charset=utf-8")
            if method == "GET" and path.startswith("/report-file/"):
                # <img> cannot send the header, so screenshots take the token in the URL.
                f = app.engine.report_file(path.rsplit("/", 1)[1]) if query == "t=" + app.token else None
                if f is None:
                    return self._send(404, {"error": "not found"})
                return self._send(200, f.read_bytes(), IMAGE_TYPES[f.suffix.lower()])
            # The token stops any other web page open on this PC from driving the tool.
            if not secrets.compare_digest(self.headers.get("X-DCSGO-Token", ""), app.token):
                return self._send(403, {"error": "forbidden"})
            body = {}
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}") if n < 65536 else {}
            try:
                self._send(200, app.handle(method, path, body))
            except KeyError:
                self._send(404, {"error": "not found"})
            except Exception as e:
                self._send(400, {"error": str(e)})

        def do_GET(self):
            self._route("GET")

        def do_POST(self):
            self._route("POST")

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    from . import winproc
    if winproc.restart_through_explorer():     # opened from a browser that passes on PreferSystem32
        return
    app = App()
    server = make_server(app)
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={app.token}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=app.check_for_update, daemon=True).start()
    try:
        import webview  # pywebview
        webview.create_window(f"DCS Graphics Optimizer {__version__}", url, width=980, height=860,
                              maximized=bool(os.environ.get("DCSTUNE_MAXIMIZED")))
        webview.start()
    except ImportError:
        webbrowser.open(url)
        print("DCS Graphics Optimizer is open in your browser. Close this window to quit.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
    server.shutdown()


if __name__ == "__main__":
    main()
