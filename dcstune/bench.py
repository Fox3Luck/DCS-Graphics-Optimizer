"""Run one benchmark: write trial settings, launch DCS, let the hook drive the scenes,
collect frame times and GPU memory, and always put the player's files back."""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .optionslua import TrialSession
from .sysinfo import NO_WINDOW

ROOT = Path(__file__).resolve().parent.parent
HOOK_SRC = ROOT / "hook" / "dcstune_bench.lua"
MISSION_SRC = ROOT / "mission" / "dcstune_bench.miz"
HOOK_NAME = "dcstune_bench.lua"
SCENES = [
    {"name": "city", "unit": "TUNE-CITY-1", "back": 35, "up": 8},
    {"name": "airfield", "unit": "TUNE-RAMP-1", "back": 28, "up": 5, "side": 10},
    {"name": "clouds", "unit": "TUNE-HIGH-1", "back": 40, "up": 10},
]
STUTTER_FACTOR = 2.5     # a frame this many times the median counts as a stutter


class BenchError(RuntimeError):
    pass


def frame_stats(frame_ms: list[float]) -> dict:
    if len(frame_ms) < 30:
        raise BenchError(f"only {len(frame_ms)} frames recorded")
    ordered = sorted(frame_ms)
    n = len(ordered)
    median = ordered[n // 2]
    # 1% low = frame rate at the 99th-percentile frame time. Measured on the test PC this
    # repeats within a few percent; averaging the slowest 1% instead swung by 2x between
    # identical runs because a handful of scenery-loading hitches dominate it.
    p99 = ordered[min(n - 1, int(n * 0.99))]
    return {
        "frames": n,
        "avg_fps": round(1000.0 * n / sum(ordered), 2),
        "p1_low_fps": round(1000.0 / p99, 2),
        "median_ms": round(median, 3),
        "max_ms": round(ordered[-1], 3),
        "stutters": sum(1 for x in frame_ms if x > STUTTER_FACTOR * median),
    }


def parse_result(raw: dict) -> dict:
    if not raw.get("ok"):
        raise BenchError("benchmark did not finish: " + (raw.get("reason") or "unknown"))
    scenes = []
    for s in raw["scenes"]:
        stats = frame_stats([float(x) for x in s["frame_ms"]])
        stats.update(name=s["name"], shot=s.get("shot") or None)
        scenes.append(stats)
    return {"scenes": scenes, "clock": raw.get("clock"), "tag": raw.get("tag")}


def dcs_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq DCS.exe", "/NH"],
                         capture_output=True, text=True, creationflags=NO_WINDOW).stdout
    return "DCS.exe" in out


class GpuSampler:
    """Peak GPU memory during a run. nvidia-smi when present, otherwise the
    vendor-neutral Windows 'GPU Adapter Memory' counter."""

    def __init__(self, interval: float = 1.0):
        self.peak_mb, self.util, self._stop = 0.0, [], threading.Event()
        self._thread = threading.Thread(target=self._loop, args=(interval,), daemon=True)
        self._nvidia = shutil.which("nvidia-smi")

    def _sample(self):
        if self._nvidia:
            out = subprocess.run([self._nvidia, "--query-gpu=memory.used,utilization.gpu",
                                  "--format=csv,noheader,nounits"], capture_output=True, text=True, creationflags=NO_WINDOW, timeout=10).stdout
            rows = [r.split(",") for r in out.strip().splitlines() if "," in r]
            if rows:
                best = max(rows, key=lambda r: float(r[0]))
                return float(best[0]), float(best[1])
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "((Get-Counter '\\GPU Adapter Memory(*)\\Dedicated Usage').CounterSamples | "
                              "Measure-Object CookedValue -Maximum).Maximum / 1MB"],
                             capture_output=True, text=True, creationflags=NO_WINDOW, timeout=20).stdout.strip()
        return (float(out), None) if out else (0.0, None)

    def _loop(self, interval):
        while not self._stop.wait(interval):
            try:
                mem, util = self._sample()
                self.peak_mb = max(self.peak_mb, mem)
                if util is not None:
                    self.util.append(util)
            except Exception:
                pass

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=15)


class Bench:
    def __init__(self, profile: dict, exe: Path, scene_sec: int = 25, settle_sec: int = 20,
                 timeout: int = 600, log=print):
        self.profile_dir = Path(profile["path"])
        self.profile_name = profile["name"]
        self.options = Path(profile["options"])
        self.exe = Path(exe)
        self.scene_sec, self.settle_sec, self.timeout, self.log = scene_sec, settle_sec, timeout, log
        self.hook_dst = self.profile_dir / "Scripts" / "Hooks" / HOOK_NAME
        self.mission_dst = self.profile_dir / "Missions" / "dcstune_bench.miz"
        self.directive = self.profile_dir / "Config" / "dcstune_directive.json"
        self.result = self.profile_dir / "Config" / "dcstune_result.json"
        self.session = TrialSession(self.options)
        self.runs = 0
        self.keep_raw_dir = None      # developer aid: keep every frame time

    # -- session lifecycle ---------------------------------------------------
    def __enter__(self):
        if dcs_running():
            raise BenchError("DCS is running. Close it first; DCS Tune never touches a running game.")
        self.session.begin()
        self.hook_dst.parent.mkdir(parents=True, exist_ok=True)
        self.mission_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(HOOK_SRC, self.hook_dst)
        shutil.copyfile(MISSION_SRC, self.mission_dst)
        return self

    def __exit__(self, *exc):
        self.cleanup()
        return False

    def cleanup(self):
        for p in (self.directive, self.result, self.hook_dst, self.mission_dst):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
        self.session.end()

    # -- one run ---------------------------------------------------------------
    def measure(self, changes: dict | None) -> dict:
        from .optimize import summarise
        self.runs += 1
        tag = f"r{self.runs:02d}"
        # Trials never change resolution, monitor layout or VR; vsync and the frame
        # cap are lifted for every run (including the baseline) so numbers compare.
        trial = {"graphics.sync": False, "graphics.maxFPS": 300}
        trial.update(changes or {})
        self.session.write_trial(trial)
        self.result.unlink(missing_ok=True)
        self.directive.write_text(json.dumps({
            "mission": str(self.mission_dst), "scenes": SCENES, "tag": tag,
            "scene_sec": self.scene_sec, "settle_sec": self.settle_sec,
            "total_timeout": self.timeout - 30}))
        args = [str(self.exe), "--no-launcher", "--force_disable_VR", "-w", self.profile_name]
        started = time.time()
        with GpuSampler() as gpu:
            proc = subprocess.Popen(args, cwd=str(self.exe.parent))
            try:
                proc.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=30)
                self.directive.unlink(missing_ok=True)
                raise BenchError("DCS did not finish the benchmark in time and was closed. "
                                 "Check that DCS starts normally and is logged in.")
        if not self.result.exists():
            self.directive.unlink(missing_ok=True)
            raise BenchError("DCS closed without writing a benchmark result (see Logs\\dcs.log, DCSTUNE lines).")
        raw_text = self.result.read_text()
        if self.keep_raw_dir:
            (Path(self.keep_raw_dir) / f"dcstune-raw-{time.strftime('%H%M%S')}-{tag}.json").write_text(raw_text)
        result = parse_result(json.loads(raw_text))
        result["vram_peak_mb"] = round(gpu.peak_mb) or None
        result["gpu_util_avg"] = round(sum(gpu.util) / len(gpu.util)) if gpu.util else None
        result["seconds"] = round(time.time() - started)
        result["changes"] = changes
        s = summarise(result)
        self.log(f"  {tag}: avg {s['avg_fps']:.0f} FPS, 1% low {s['p1_low_fps']:.0f} FPS, "
                 f"VRAM {result['vram_peak_mb']} MB, {result['seconds']}s")
        s["raw"] = result
        return s
