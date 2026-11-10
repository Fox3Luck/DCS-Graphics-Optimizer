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
        from . import sysinfo
        from .optionslua import recover
        self.info = sysinfo.collect()
        self.profile = sysinfo.pick_profile(self.info, profile_name)
        self.recovered = recover(self.profile["options"])

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

    def scorecard(self) -> dict:
        from . import rate
        from .optionslua import list_backups
        machine = rate.rate_machine(self.info)
        flat = self._flat()
        fit = rate.rate_settings(self.info, flat, machine,
                                 calibration=rate.load_calibration(self.profile, self.info, flat))
        return {"profile": self.profile["name"], "profile_dir": Path(self.profile["path"]).name,
                "hardware": rate.hardware_summary(self.info), "overall": rate.overall(machine, fit),
                "profiles": [p["name"] for p in self.info["profiles"]],
                "machine": machine,
                "settings": fit,
                "vr": bool(flat.get("VR.enable")), "recovered": self.recovered,
                "can_undo": bool(list_backups(self.profile["options"])),
                "report": self._report()}

    def optimize(self, full: bool, log) -> dict:
        from . import model as M, optimize, rate, sysinfo
        from .bench import Bench
        from .optionslua import atomic_write
        started = time.time()
        flat, gpu = self._flat(), self.info["gpu"]
        machine = rate.rate_machine(self.info)
        vendor = sysinfo.gpu_vendor(self.info)
        mdl = M.Model(machine["gpu_score"], machine["cpu_score"],
                      flat.get("graphics.width") or gpu["width"], flat.get("graphics.height") or gpu["height"], vendor)
        exe = sysinfo.dcs_exe(sysinfo.pick_install(self.info))
        with Bench(self.profile, exe, log=log) as b:
            out = optimize.run(mdl, flat, vendor, rate.target_fps(gpu.get("refresh")),
                               gpu.get("vram_mb") or 0, b.measure, full=full, log=log,
                               measure_fast=b.measure_fast, measure_batch=b.measure_batch)
            launches = b.runs
            for res in (out["before"], (out["recommended"] or {}).get("result") or {}):
                b.keep_shots.update(s["shot"] for s in (res.get("raw") or {}).get("scenes", []) if s.get("shot"))
        target = out["target_fps"]
        rate.save_calibration(self.profile, self.info, flat, out["learned"])
        base_ms = 1000.0 / out["before"]["avg_fps"]
        report = {"created": time.strftime("%Y-%m-%d %H:%M"), "profile": self.profile["name"],
                  "kind": "Thorough test" if full else "Test and optimize",
                  "duration_min": max(1, round((time.time() - started) / 60)),
                  "hardware": rate.hardware_summary(self.info),
                  "costs": optimize.measured_costs(mdl, base_ms),
                  "target_fps": target, "target_reached": out["target_reached"],
                  "keep_current": out["keep_current"], "runs": launches,
                  "disturbed": out["disturbed"],
                  "before": rate.rate_settings(self.info, flat, machine, out["before"], target),
                  "machine": machine,
                  "before_result": _slim(out["before"])}
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

    def apply(self) -> str:
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
        saved = backup(self.profile["options"])
        opts = Options.load(self.profile["options"])
        opts.update(changes)
        opts.save(self.profile["options"])
        rep["applied"] = time.strftime("%Y-%m-%d %H:%M")   # keep the report; the player may want to read it again
        atomic_write(rp, json.dumps(rep, indent=1).encode())
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
            atomic_write(self.report_path(), json.dumps(rep, indent=1).encode())
        return "Your previous settings are back."


def _slim(summary: dict) -> dict:
    return {k: summary.get(k) for k in ("avg_fps", "p1_low_fps", "vram_peak_mb")} | {
        "scenes": [{k: s.get(k) for k in ("name", "avg_fps", "p1_low_fps", "stutters", "shot")}
                   for s in (summary.get("raw") or summary).get("scenes", [])]}


class App:
    """Holds the single background job (optimize) and its progress log."""

    def __init__(self, engine_factory=Engine):
        self.token = secrets.token_urlsafe(16)
        self._factory, self._engine = engine_factory, None
        self.lock = threading.Lock()
        self.job = {"state": "idle", "log": [], "error": None, "report": None}

    @property
    def engine(self):
        if self._engine is None:
            self._engine = self._factory()
        return self._engine

    def start_optimize(self, full: bool) -> None:
        with self.lock:
            if self.job["state"] == "running":
                raise RuntimeError("A test is already running.")
            self.job = {"state": "running", "log": [], "error": None, "report": None, "started": time.time()}
        threading.Thread(target=self._work, args=(full,), daemon=True).start()

    def _work(self, full):
        job = self.job
        try:
            job["report"] = self.engine.optimize(full, lambda m: job["log"].append(str(m)))
            job["state"] = "done"
        except Exception as e:
            job["error"], job["state"] = str(e), "failed"

    def handle(self, method: str, path: str, body: dict) -> dict:
        if method == "GET" and path == "/api/scorecard":
            from . import report as R
            sc = self.engine.scorecard()
            if sc.get("report") and sc["report"].get("before"):
                sc["report_html"] = R.fragment(sc["report"], lambda name: f"/report-file/{name}?t={self.token}")
            return sc
        if method == "GET" and path == "/api/job":
            return self.job
        if method == "POST" and path == "/api/optimize":
            self.start_optimize(bool(body.get("full")))
            return {"ok": True}
        if method == "POST" and path == "/api/apply":
            return {"message": self.engine.apply()}
        if method == "POST" and path == "/api/undo":
            return {"message": self.engine.undo()}
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
    app = App()
    server = make_server(app)
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={app.token}"
    threading.Thread(target=server.serve_forever, daemon=True).start()
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
