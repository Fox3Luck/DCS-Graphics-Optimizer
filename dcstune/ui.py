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

    def scorecard(self) -> dict:
        from . import rate
        from .optionslua import list_backups
        machine = rate.rate_machine(self.info)
        flat = self._flat()
        rp = self.report_path()
        fit = rate.rate_settings(self.info, flat, machine,
                                 calibration=rate.load_calibration(self.profile, self.info, flat))
        return {"profile": self.profile["name"],
                "hardware": rate.hardware_summary(self.info), "overall": rate.overall(machine, fit),
                "profiles": [p["name"] for p in self.info["profiles"]],
                "machine": machine,
                "settings": fit,
                "vr": bool(flat.get("VR.enable")), "recovered": self.recovered,
                "can_undo": bool(list_backups(self.profile["options"])),
                "report": json.loads(rp.read_text()) if rp.exists() else None}

    def optimize(self, full: bool, log) -> dict:
        from . import model as M, optimize, rate, sysinfo
        from .bench import Bench
        from .optionslua import atomic_write
        flat, gpu = self._flat(), self.info["gpu"]
        machine = rate.rate_machine(self.info)
        vendor = sysinfo.gpu_vendor(self.info)
        mdl = M.Model(machine["gpu_score"], machine["cpu_score"],
                      flat.get("graphics.width") or gpu["width"], flat.get("graphics.height") or gpu["height"], vendor)
        exe = sysinfo.dcs_exe(sysinfo.pick_install(self.info))
        with Bench(self.profile, exe, log=log) as b:
            out = optimize.run(mdl, flat, vendor, rate.target_fps(gpu.get("refresh")),
                               gpu.get("vram_mb") or 0, b.measure, full=full, log=log,
                               measure_fast=b.measure_fast)
            for res in (out["before"], (out["recommended"] or {}).get("result") or {}):
                b.keep_shots.update(s["shot"] for s in (res.get("raw") or {}).get("scenes", []) if s.get("shot"))
        target = out["target_fps"]
        rate.save_calibration(self.profile, self.info, flat, out["learned"])
        report = {"created": time.strftime("%Y-%m-%d %H:%M"), "profile": self.profile["name"],
                  "target_fps": target, "target_reached": out["target_reached"],
                  "keep_current": out["keep_current"], "runs": len(out["history"]) + 1,
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
                          change_list=optimize.describe_changes(flat, rec["changes"]))
        report["overall_before"] = rate.overall(machine, report["before"])
        if "after" in report:
            report["overall_after"] = rate.overall(machine, report["after"])
        atomic_write(self.report_path(), json.dumps(report, indent=1).encode())
        return report

    def apply(self) -> str:
        from .bench import dcs_running
        from .optionslua import Options, backup
        if dcs_running():
            raise RuntimeError("Close DCS first. It overwrites its settings file when it exits.")
        rp = self.report_path()
        changes = json.loads(rp.read_text()).get("changes") if rp.exists() else None
        if not changes:
            raise RuntimeError("There is no recommendation to apply yet.")
        saved = backup(self.profile["options"])
        opts = Options.load(self.profile["options"])
        opts.update(changes)
        opts.save(self.profile["options"])
        rp.unlink()     # the recommendation is now the current settings
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
            return self.engine.scorecard()
        if method == "GET" and path == "/api/job":
            return self.job
        if method == "POST" and path == "/api/optimize":
            self.start_optimize(bool(body.get("full")))
            return {"ok": True}
        if method == "POST" and path == "/api/apply":
            return {"message": self.engine.apply()}
        if method == "POST" and path == "/api/undo":
            return {"message": self.engine.undo()}
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
                return self._send(200, PAGE.read_bytes().replace(b"__TOKEN__", app.token.encode()),
                                  "text/html; charset=utf-8")
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
