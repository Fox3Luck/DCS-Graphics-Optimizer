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
                               hz=prefs.get_pref(self.profile, "headset_hz"))
        self.info["fps_goal"] = prefs.get_pref(self.profile, "fps_goal")

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
        return (f"Headset refresh rate set to {hz} Hz. The scorecard and the test now aim for {hz} FPS." if hz
                else "Headset refresh rate set back to automatic.")

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
                "vr_tested": bool(st) and V.bench_enabled(), "vr_test_build": V.test_build(),
                "headset": st and {"name": st["headset"], "detected": st["detected"],
                                   "choices": V.headset_names(), "refresh": st["refresh"],
                                   "hz": st["target"], "hz_chosen": st["hz_chosen"]},
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

    def optimize(self, full: bool, log, mode: str = "balanced") -> dict:
        from . import audit, model as M, optimize, rate, sysinfo, vr as V
        from .bench import Bench, other_vram_high
        from .optionslua import atomic_write
        started = time.time()
        flat, gpu = self._flat(), self.info["gpu"]
        self._flat_at_test = dict(flat)       # the player's real settings, for the audit file
        st = V.state(self.info, flat)
        vr_skipped = bool(st) and not V.bench_enabled()
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
        own_goal = (st["target"] if st["hz_chosen"] else None) if st else rate.chosen_goal(self.info)
        if own_goal:
            log(f"Your own goal: {own_goal} FPS" + (" (the refresh rate you picked for your headset)." if st else "."))
        extra = V.fixed_changes(st, flat) if st else None
        if extra and "VR.pixel_density" in extra:      # candidates are judged at the density they will use
            mdl.vr = dict(mdl.vr, pd=extra["VR.pixel_density"])
        # Reuse what an earlier thorough test measured on this PC (same card, processor and
        # resolution); a thorough test re-measures and overwrites it.
        cal = rate.load_calibration(self.profile, self.info, flat)
        if cal and not full:
            mdl.measured = {k: {int(i): ms for i, ms in v.items()} for k, v in cal.get("measured", {}).items()}
        exe = sysinfo.dcs_exe(sysinfo.pick_install(self.info))
        with Bench(self.profile, exe, log=log, vr=bool(st), vram_total_mb=gpu.get("vram_mb") or 0) as b:
            out = optimize.run(mdl, flat, vendor, goal,
                               gpu.get("vram_mb") or 0, b.measure, full=full, log=log,
                               measure_fast=b.measure_fast, measure_batch=b.measure_batch,
                               steps=st and st["steps"], extra=extra, mode=mode)
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

    def _work(self, full, mode="balanced"):
        job = self.job
        chime("start")
        try:
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
        if method == "POST" and path == "/api/apply":
            skip = body.get("skip")
            return {"message": self.engine.apply(body.get("vr_ok") is True,
                                                 skip if isinstance(skip, list) else ())}
        if method == "POST" and path == "/api/headset":
            with self.lock:
                if self.job["state"] == "running":
                    raise RuntimeError("A test is running; pick the headset after it finishes.")
            return {"message": self.engine.set_headset(body.get("name"))}
        if method == "POST" and path in ("/api/headset-hz", "/api/goal"):
            with self.lock:
                if self.job["state"] == "running":
                    raise RuntimeError("A test is running; change the goal after it finishes.")
            if path == "/api/goal":
                return {"message": self.engine.set_goal(body.get("fps"))}
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
        webview.create_window("DCS Graphics Optimizer", url, width=980, height=860,
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
