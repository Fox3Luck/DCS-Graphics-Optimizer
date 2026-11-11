"""Run one benchmark: write trial settings, launch DCS, let the hook drive the scenes,
collect frame times and GPU memory, and always put the player's files back."""
from __future__ import annotations

import json
import os
import secrets
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
KEY_MARK = "@DCSTUNE_KEY@"          # in the bundled hook; replaced by a random key on install
DIRECTIVE_VALID_SEC = 600           # DCS has to read the directive within this time
SCENES = [
    {"name": "city", "unit": "TUNE-CITY-1", "back": 35, "up": 8},
    {"name": "airfield", "unit": "TUNE-RAMP-1", "back": 28, "up": 5, "side": 10},
    {"name": "clouds", "unit": "TUNE-HIGH-1", "back": 40, "up": 10},
]
BATCH_SETTLE_SEC = 10     # wait before timing in every measured no-restart trial
QUICK_EXIT_SEC = 45       # DCS gone this fast without a result = it never really started
SHORT_SCENE_SEC, SHORT_LEAD_SEC = 10, 2   # cost-only runs: averages repeat within 0.2% at 10 s
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
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq DCS.exe", "/NH"],
                             capture_output=True, text=True, creationflags=NO_WINDOW).stdout
    except FileNotFoundError:      # not Windows (the automated tests)
        return False
    return "DCS.exe" in out


class GpuSampler:
    """Peak GPU memory during a run. nvidia-smi when present, otherwise the
    vendor-neutral Windows 'GPU Adapter Memory' counter."""

    def __init__(self, interval: float = 1.0):
        self.peak_mb, self.util, self._stop = 0.0, [], threading.Event()
        self._thread = threading.Thread(target=self._loop, args=(interval,), daemon=True)
        # DCSTUNE_NO_NVSMI: testing switch to exercise the AMD/Intel counter path on an NVIDIA PC
        self._nvidia = None if os.environ.get("DCSTUNE_NO_NVSMI") else shutil.which("nvidia-smi")

    def _sample(self):
        if self._nvidia:
            out = subprocess.run([self._nvidia, "--query-gpu=memory.used,utilization.gpu",
                                  "--format=csv,noheader,nounits"], capture_output=True, text=True, creationflags=NO_WINDOW, timeout=10).stdout
            rows = [r.split(",") for r in out.strip().splitlines() if "," in r]
            if rows:
                best = max(rows, key=lambda r: float(r[0]))
                return float(best[0]), float(best[1])
        # Any vendor: Windows' own counters. Memory = the busiest adapter; load = the busiest
        # single process's 3D engine use (what Task Manager shows as GPU %).
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "$c = (Get-Counter '\\GPU Adapter Memory(*)\\Dedicated Usage','\\GPU Engine(*engtype_3D)\\Utilization Percentage' "
                              "-ErrorAction SilentlyContinue).CounterSamples; "
                              "$m = ($c | ? Path -like '*dedicated usage' | Measure-Object CookedValue -Maximum).Maximum / 1MB; "
                              "$u = ($c | ? Path -like '*utilization percentage' | Group-Object { ($_.InstanceName -split '_')[1] } | "
                              "% { ($_.Group | Measure-Object CookedValue -Sum).Sum } | Measure-Object -Maximum).Maximum; "
                              "'{0:F0},{1:F1}' -f $m, $u"],
                             capture_output=True, text=True, creationflags=NO_WINDOW, timeout=20).stdout.strip()
        mem, _, util = out.partition(",")
        return (float(mem), float(util) if util else None) if mem else (0.0, None)

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


BUSY_GPU_PERCENT = 25     # refuse to test above this while DCS is not even running


def gpu_idle_check(samples: int = 4) -> tuple[float, float]:
    """(average GPU load %, video memory in use MB) right now, before DCS starts."""
    sampler = GpuSampler()
    loads, mem = [], 0.0
    for _ in range(samples):
        try:
            m, util = sampler._sample()
        except Exception:
            return 0.0, 0.0
        mem = max(mem, m)
        if util is not None:
            loads.append(util)
        time.sleep(0.7)
    return (sum(loads) / len(loads) if loads else 0.0), mem


def remove_leftovers(profile_dir) -> list[str]:
    """Delete everything a test puts into the DCS profile (the hook, the mission, the directive
    and the result). Called at the end of every test and whenever the program starts, so an
    interrupted test cannot leave the hook installed. Returns the names that were removed."""
    d = Path(profile_dir)
    gone = []
    for p in (d / "Config" / "dcstune_directive.json", d / "Config" / "dcstune_result.json",
              d / "Scripts" / "Hooks" / HOOK_NAME, d / "Missions" / "dcstune_bench.miz"):
        try:
            p.unlink()
            gone.append(p.name)
        except FileNotFoundError:
            pass
        except OSError:
            pass          # locked by a running DCS; the hook also removes itself when it has no directive
    return gone


def free_port() -> int:
    """A random high port nothing is listening on, for the local session of one DCS start."""
    import socket
    rng = secrets.SystemRandom()
    for _ in range(50):
        port = rng.randrange(20000, 60000)
        try:
            for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
                with socket.socket(socket.AF_INET, kind) as s:
                    s.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
    raise BenchError("Could not find a free network port on this PC for the test.")


class Bench:
    def __init__(self, profile: dict, exe: Path, scene_sec: int = 25, settle_sec: int = 20,
                 timeout: int = 600, log=print, vr: bool = False):
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
        self.vr = vr                  # start DCS in the headset (experimental, see vr.py)
        self.session_id = time.strftime("%m%d%H%M")   # makes this session's screenshots identifiable
        self.keep_shots: set[str] = set()             # screenshot names to leave for the player
        self.allow_busy = bool(os.environ.get("DCSTUNE_ALLOW_BUSY"))   # developer override
        self.other_vram_mb = 0.0
        self.keep_raw_dir = None      # developer aid: keep every frame time

    # -- session lifecycle ---------------------------------------------------
    def __enter__(self):
        if dcs_running():
            raise BenchError("DCS is running. Close it first; DCS Graphics Optimizer never touches a running game.")
        load, self.other_vram_mb = gpu_idle_check()
        if load > BUSY_GPU_PERCENT and not self.allow_busy:
            raise BenchError(f"Another program is using your graphics card ({load:.0f}% busy before DCS has even "
                             "started). Close games, video renders, AI tools and browser videos, then try again; "
                             "otherwise the results would be wrong.")
        if load > BUSY_GPU_PERCENT:
            self.log(f"WARNING: graphics card is {load:.0f}% busy before DCS starts; results will be unreliable.")
        self.session.begin()
        self.hook_dst.parent.mkdir(parents=True, exist_ok=True)
        self.mission_dst.parent.mkdir(parents=True, exist_ok=True)
        # Each installed copy of the hook gets its own key; it obeys only a directive that carries it.
        self.key = secrets.token_hex(16)
        hook = HOOK_SRC.read_text(encoding="utf-8")
        if hook.count(KEY_MARK) != 1:
            raise BenchError("The benchmark script inside this program is damaged.")
        self.hook_dst.write_text(hook.replace(KEY_MARK, self.key), encoding="utf-8", newline="")
        shutil.copyfile(MISSION_SRC, self.mission_dst)
        return self

    def __exit__(self, *exc):
        self.cleanup()
        return False

    def cleanup(self):
        remove_leftovers(self.profile_dir)
        # A test makes three screenshots per DCS launch; leave only the ones asked for
        # (before / recommended) in the player's ScreenShots folder.
        # When this session produced a new before/recommended pair, older sessions' pairs go too.
        pattern = "dcstune_*" if self.keep_shots else f"dcstune_{self.session_id}r*"
        for shot in (self.profile_dir / "ScreenShots").glob(pattern):
            if shot.stem not in self.keep_shots:
                try:
                    shot.unlink()
                except OSError:
                    pass
        self.session.end()

    # -- one run ---------------------------------------------------------------
    def measure_fast(self, changes: dict | None) -> dict:
        """Shorter scenes, for runs where only the average frame rate is needed."""
        return self.measure(changes, short=True)

    def measure(self, changes: dict | None, short: bool = False) -> dict:
        from .optimize import summarise
        self.runs += 1
        tag = f"{self.session_id}r{self.runs:02d}"
        raw, gpu, seconds = self._launch(changes, {"tag": tag}, short, self.timeout)
        result = parse_result(raw)
        result["vram_peak_mb"] = round(gpu.peak_mb) or None
        result["vram_other_mb"] = round(self.other_vram_mb)      # already in use before DCS started
        result["gpu_util_avg"] = round(sum(gpu.util) / len(gpu.util)) if gpu.util else None
        result["seconds"] = seconds
        result["changes"] = changes
        s = summarise(result)
        self.log(f"  {tag}: avg {s['avg_fps']:.0f} FPS, 1% low {s['p1_low_fps']:.0f} FPS, "
                 f"VRAM {result['vram_peak_mb']} MB, {seconds}s")
        s["raw"] = result
        return s

    def measure_batch(self, changes_list: list[dict | None]) -> list[dict]:
        """Average frame rate for several settings changes in ONE DCS launch (only the
        mission restarts between them). Each entry is a dict of dotted option keys, or
        None for the player's own settings. Must not contain restart-only settings."""
        from .optionslua import Options
        cur = Options.load(self.session.saved).section("graphics")
        bare = lambda c: {k.split(".", 1)[1]: v for k, v in (c or {}).items()}
        keys = {k for c in changes_list for k in bare(c)}
        base = {k: cur[k] for k in keys if k in cur}
        # First a warm-up trial that is thrown away: it absorbs texture loading, and it lets
        # every measured trial use the same short wait. (The wait decides where the
        # aircraft is when timing starts, so trials with different waits do not compare.)
        trials = [{"tag": "warm", "set": dict(base), "settle_sec": self.settle_sec}]
        for n, c in enumerate(changes_list):
            # every trial states every involved option, so the previous trial's change is undone
            trials.append({"tag": f"t{n:02d}", "set": dict(base, **bare(c)), "settle_sec": BATCH_SETTLE_SEC})
        return [{"avg_fps": r["avg_fps"]} for r in self.run_trials(trials, screenshots=False)[1:]]

    def run_trials(self, trials: list[dict], short: bool = True, screenshots: bool = True) -> list[dict]:
        """Several settings trials in ONE DCS launch (only the mission restarts).
        trials: [{"tag": "a", "set": {"shadows": 0}}, ...] - bare graphics option names.
        Returns one {"tag", "applied", "scenes": [stats...]} per trial."""
        self.runs += 1
        named = [dict(t, tag=f"{self.session_id}r{self.runs:02d}{t['tag']}") for t in trials]
        raw, gpu, seconds = self._launch(None, {"tag": named[0]["tag"], "trials": named,
                                                "screenshots": screenshots}, short, 150 + 100 * len(trials))
        if not raw.get("ok"):
            raise BenchError("benchmark did not finish: " + (raw.get("reason") or "unknown"))
        out = []
        for t, src in zip(raw["trials"], trials):
            scenes = [dict(frame_stats([float(x) for x in sc["frame_ms"]]), name=sc["name"]) for sc in t["scenes"]]
            out.append({"tag": src["tag"], "applied": t["applied"], "scenes": scenes,
                        "avg_fps": round(sum(sc["avg_fps"] for sc in scenes) / len(scenes), 2)})
        self.log(f"  {len(out)} trials in {seconds}s, VRAM peak {round(gpu.peak_mb)} MB")
        return out

    def _keep_failure_log(self):
        try:
            shutil.copyfile(self.profile_dir / "Logs" / "dcs.log",
                            self.profile_dir / "Config" / "dcstune-last-failure.log")
        except OSError:
            pass

    def _launch(self, changes, directive_extra: dict, short: bool, timeout: int):
        # Trials never change resolution, monitor layout or VR; vsync and the frame
        # cap are lifted for every run (including the baseline) so numbers compare.
        trial = {"graphics.sync": False, "graphics.maxFPS": 300}
        trial.update(changes or {})
        self.session.write_trial(trial)
        self.result.unlink(missing_ok=True)

        def directive() -> str:
            # New for every DCS start: the key of the installed hook, a short validity, and the
            # password and port of the local session DCS has to host to run the mission.
            return json.dumps(dict({
                "key": self.key, "not_after": int(time.time()) + DIRECTIVE_VALID_SEC,
                "password": secrets.token_hex(16), "port": free_port(),
                "mission": str(self.mission_dst), "scenes": SCENES,
                "scene_sec": SHORT_SCENE_SEC if short else self.scene_sec,
                "scene_lead_sec": SHORT_LEAD_SEC if short else 4, "settle_sec": self.settle_sec,
                "total_timeout": timeout - 30}, **directive_extra))
        self.directive.write_text(directive())
        args = [str(self.exe), "--no-launcher", "--force_enable_VR" if self.vr else "--force_disable_VR",
                "-w", self.profile_name]
        started = time.time()
        for attempt in (1, 2):
            if attempt == 2:
                self.log("  DCS closed straight away; waiting a moment and starting it again...")
                time.sleep(15)
                self.directive.write_text(directive())
            launched = time.time()
            with GpuSampler() as gpu:
                proc = subprocess.Popen(args, cwd=str(self.exe.parent))
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=30)
                    self.directive.unlink(missing_ok=True)
                    self._keep_failure_log()
                    raise BenchError("DCS did not finish the benchmark in time and was closed. "
                                     "Check that DCS starts normally and is logged in.")
            if self.result.exists() or time.time() - launched > QUICK_EXIT_SEC:
                break
        time.sleep(3)      # let DCS finish releasing its files before anything else starts
        if not self.result.exists():
            self.directive.unlink(missing_ok=True)
            self._keep_failure_log()
            raise BenchError("DCS closed without writing a benchmark result "
                             "(a copy of its log is in Config\\dcstune-last-failure.log).")
        raw_text = self.result.read_text()
        if self.keep_raw_dir:
            (Path(self.keep_raw_dir) / f"dcstune-raw-{time.strftime('%H%M%S')}-{directive_extra['tag']}.json").write_text(raw_text)
        return json.loads(raw_text), gpu, round(time.time() - started)
