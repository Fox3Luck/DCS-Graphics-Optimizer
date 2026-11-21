# DCS Graphics Optimizer - Fox3 Managed Solutions Inc.
# Created 2026-11-10. Runs one benchmark: starts DCS, measures the scenes, puts the player's files back.
"""Run one benchmark: write trial settings, launch DCS, let the hook drive the scenes,
collect frame times and GPU memory, and always put the player's files back."""
from __future__ import annotations

import atexit
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from pathlib import Path, PureWindowsPath

from . import winproc
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
# Only when the player asked for it (issues #23, #35): a slow helicopter low along the runway of a
# busy airfield. The camera sits well behind and above so the vehicles, aircraft and smoke ahead are in view.
BUSY_SCENE = {"name": "busy", "unit": "TUNE-BUSY-1", "back": 60, "up": 22}
BATCH_SETTLE_SEC = 10     # wait before timing in every measured no-restart trial
QUICK_EXIT_SEC = 45       # DCS gone this fast without a result = it never really started
EXIT_GRACE_SEC = 45       # result written: how long DCS gets to close itself before the tool closes it
# Past the deadline, DCS still gets more time while its log keeps growing: an add-on can hold the
# game for minutes doing one-time work (a beta 20 log: Tacview exporting its terrain files froze
# the mission for six and a half minutes, and the test ran out of time with the aircraft in place).
LOG_ACTIVE_SEC = 120
BUSY_EXTRA_SEC = 900
HANDOFF_WAIT_SEC = 25     # after such an exit, how long to look for a DCS that Steam/the updater started instead
STEAM_PROMPT_WAIT_SEC = 300   # Steam asks the player to OK the launch options first; give them time to click (#27)
STEAM_RESTART = "Steam asked for app restart"   # DCS writes this when it hands its start over to Steam
STEAM_APP_ID = "223750"        # DCS World Steam Edition
STEAM_ENV = ("SteamAppId", "SteamGameId")
SHORT_SCENE_SEC, SHORT_LEAD_SEC = 10, 2   # cost-only runs: averages repeat within 0.2% at 10 s
STUTTER_FACTOR = 2.5     # a frame this many times the median counts as a stutter


class BenchError(RuntimeError):
    fatal = False          # True: no point trying more runs in this test (the whole test stops)


class DcsWontStart(BenchError):
    """DCS closes as soon as it is started, every time (beta issue #17). Further runs would
    only repeat it, so the test stops instead of looking like it loops."""
    fatal = True


class DcsCrashed(BenchError):
    """DCS crashed (it wrote a crash report into its log). The player's settings are put back at
    once and the test stops: more runs would only crash again (issue #58)."""
    fatal = True


CRASH_MARK = b"Minidump created"      # DCS writes this into dcs.log when it crashes


def crash_message(during_startup: bool) -> str:
    when = "during startup" if during_startup else "during the test"
    return (f"DCS crashed {when}, so the test was stopped. Your settings have been put back. A copy of DCS's "
            "log is in Config\\dcstune-last-failure.log; if DCS starts normally on its own, please send us that "
            "log (GitHub issue or the Discord channel).")


# Tests that are running now. If the window is closed or the program ends mid-test, stop_open_tests()
# ends DCS and puts the player's options.lua back: the test runs on a background thread, which never
# gets to its own clean-up when the program ends (issue #58).
_open_benches: set = set()
_open_lock = threading.Lock()


def stop_open_tests(*_) -> int:
    """End every test still running: close the DCS it started and put the player's files back.
    Safe to call any number of times. Returns how many tests were stopped."""
    with _open_lock:
        benches = list(_open_benches)
    for b in benches:
        try:
            b.abort()
        except Exception:
            pass
    return len(benches)


atexit.register(stop_open_tests)


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
        if s.get("w0") and s.get("w1"):
            stats.update(w0=s["w0"], w1=s["w1"])
        scenes.append(stats)
    return {"scenes": scenes, "clock": raw.get("clock"), "tag": raw.get("tag")}


def _taskkill_dcs() -> None:
    try:
        winproc.run(["taskkill", "/IM", "DCS.exe", "/F"], capture_output=True, creationflags=NO_WINDOW)
    except FileNotFoundError:
        pass


NEEDS_ADMIN = ("Windows only starts your DCS as administrator, and the optimizer was started normally, so it "
               "could not start DCS. Either close the optimizer, right-click it and choose \"Run as administrator\", "
               "or switch that off for DCS: right-click DCS.exe (in the bin-mt folder of your DCS install), "
               "Properties, Compatibility, untick \"Run this program as an administrator\". Then test again. "
               "Nothing was changed.")


def is_steam_exe(exe) -> bool:
    """True for a DCS.exe inside a Steam library (...\\steamapps\\common\\DCSWorld\\bin-mt\\DCS.exe)."""
    return "steamapps" in (part.lower() for part in PureWindowsPath(str(exe)).parts)


def steam_launch_env(base=None) -> dict:
    """The environment for a Steam-edition DCS.exe: this program's own, plus the app id Steam gives
    every game it starts. With it DCS keeps running in the process the tool started instead of
    closing and asking Steam to start it again behind a "launch with custom arguments" box (#27;
    approach suggested with a patch by the issue's reporter). Names are case-insensitive on Windows,
    so any existing spelling is dropped first."""
    base = os.environ if base is None else base
    drop = {n.upper() for n in STEAM_ENV}
    env = {k: v for k, v in base.items() if k.upper() not in drop}
    env.update({n: STEAM_APP_ID for n in STEAM_ENV})
    return env


def steam_running() -> bool:
    try:
        out = winproc.run(["tasklist", "/FI", "IMAGENAME eq steam.exe", "/NH"],
                          capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW).stdout
    except FileNotFoundError:      # not Windows (the automated tests)
        return True
    return "steam.exe" in (out or "").lower()


def dcs_running() -> bool:
    try:
        out = winproc.run(["tasklist", "/FI", "IMAGENAME eq DCS.exe", "/NH"],
                          capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW).stdout
    except FileNotFoundError:      # not Windows (the automated tests)
        return False
    # errors="replace": on a non-English Windows tasklist's text can hold characters the
    # default code page cannot decode, which used to leave out as None (beta issue #8).
    return "DCS.exe" in (out or "")


PIMAX_HOME_EXE = "PimaxHome-Win64-Shipping.exe"
PIMAX_HOME_RUNNING = (
    "Pimax Home (Pimax's 3D lobby) is running. Close it before testing in the headset: it draws its own 3D world on the "
    "graphics card and holds several GB of video memory, so DCS can run short and the results can come out "
    "too low. In Pimax Play, switch Pimax Home off in the settings, so it doesn't start again by itself "
    "after every VR program. If it is still running now, open Task Manager, "
    "go to the Details tab, select PimaxHome-Win64-Shipping.exe and click End task. Keep Pimax Play itself "
    "running (and pi_server.exe, the headset's runtime): the test needs them. Then try again.")


def pimax_home_running() -> bool:
    """Is Pimax's 3D home screen running? (Joe, 2026-11-20, after the first Crystal Light tests: it
    must not run during a headset test.)"""
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {PIMAX_HOME_EXE}", "/NH"],
                             capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW).stdout
    except Exception:              # not Windows (the automated tests), or tasklist failed: never block on it
        return False
    return PIMAX_HOME_EXE.lower() in (out or "").lower()


class GpuSampler:
    """Peak GPU memory during a run. nvidia-smi when present, otherwise the
    vendor-neutral Windows 'GPU Adapter Memory' counter."""

    def __init__(self, interval: float = 1.0, heat: bool = False):
        self.peak_mb, self.util, self._stop = 0.0, [], threading.Event()
        # Heat check only (#23): every few seconds, the graphics card's temperature, clock and power
        # (NVIDIA driver) and how fast Windows lets the processor run (any PC).
        self.heat: list[dict] = []
        self._heat_thread = threading.Thread(target=self._heat_loop, daemon=True) if heat else None
        self.samples: list[tuple[float, float]] = []      # (time, load %), to match to scenes
        self._thread = threading.Thread(target=self._loop, args=(interval,), daemon=True)
        # DCSTUNE_NO_NVSMI: testing switch to exercise the AMD/Intel counter path on an NVIDIA PC
        self._nvidia = None if os.environ.get("DCSTUNE_NO_NVSMI") else shutil.which("nvidia-smi")
        # The load matched to scenes always comes from Windows' counter (Task Manager's GPU %):
        # on the test PC nvidia-smi said 99% both at 4K DLAA (97 FPS) and with everything
        # turned down (256 FPS), where Windows said 96% and 90% (#31). With nvidia-smi present
        # it runs in its own thread so memory sampling keeps its pace.
        self._load_thread = (threading.Thread(target=self._load_loop, args=(interval,), daemon=True)
                             if self._nvidia else None)

    def _sample(self, nvidia: bool = True):
        if self._nvidia and nvidia:
            out = winproc.run([self._nvidia, "--query-gpu=memory.used,utilization.gpu",
                               "--format=csv,noheader,nounits"], capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW, timeout=10).stdout
            rows = [r.split(",") for r in out.strip().splitlines() if "," in r]
            if rows:
                best = max(rows, key=lambda r: float(r[0]))
                return float(best[0]), float(best[1])
        # Any vendor: Windows' own counters. Memory = the busiest adapter; load = the busiest
        # single process's 3D engine use (what Task Manager shows as GPU %). Get-Counter only
        # knows the English counter names, which Windows translates in other languages (#21),
        # so when it finds nothing the same counters are read through their WMI classes,
        # whose names are never translated.
        out = winproc.run(["powershell", "-NoProfile", "-Command",
                           "$c = (Get-Counter '\\GPU Adapter Memory(*)\\Dedicated Usage','\\GPU Engine(*engtype_3D)\\Utilization Percentage' "
                           "-ErrorAction SilentlyContinue).CounterSamples; "
                           "$m = ($c | ? Path -like '*dedicated usage' | Measure-Object CookedValue -Maximum).Maximum / 1MB; "
                           "$u = ($c | ? Path -like '*utilization percentage' | Group-Object { ($_.InstanceName -split '_')[1] } | "
                           "% { ($_.Group | Measure-Object CookedValue -Sum).Sum } | Measure-Object -Maximum).Maximum; "
                           "if (-not $m) { "
                           "$m = (Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUAdapterMemory -ErrorAction SilentlyContinue | "
                           "Measure-Object DedicatedUsage -Maximum).Maximum / 1MB; "
                           "$u = (Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine -ErrorAction SilentlyContinue | "
                           "? Name -like '*engtype_3D' | Group-Object { ($_.Name -split '_')[1] } | "
                           "% { ($_.Group | Measure-Object UtilizationPercentage -Sum).Sum } | Measure-Object -Maximum).Maximum }; "
                           "[string]::Format([Globalization.CultureInfo]::InvariantCulture, '{0:F0};{1:F1}', $m, $u)"],
                          capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW, timeout=20).stdout.strip()
        # Invariant culture and ";": a German or French Windows writes decimals with a comma.
        mem, _, util = out.partition(";")
        try:
            return (float(mem), float(util) if util else None) if mem else (0.0, None)
        except ValueError:
            return 0.0, None

    def _heat_sample(self) -> dict:
        row = {"t": time.time(), "gpu_temp": None, "gpu_clock": None, "gpu_power": None, "cpu_speed": None}
        if self._nvidia:
            out = winproc.run([self._nvidia, "--query-gpu=temperature.gpu,clocks.gr,power.draw",
                               "--format=csv,noheader,nounits"], capture_output=True, text=True, errors="replace",
                              creationflags=NO_WINDOW, timeout=10).stdout
            rows = [[c.strip() for c in r.split(",")] for r in out.strip().splitlines() if r.count(",") == 2]
            for key, i in (("gpu_temp", 0), ("gpu_clock", 1), ("gpu_power", 2)):
                vals = []
                for r in rows:
                    try:
                        vals.append(float(r[i]))
                    except ValueError:              # "[N/A]" on cards that do not report it
                        pass
                if vals:
                    row[key] = max(vals)
        # Processor speed as a percentage of its rated speed (above 100 with turbo; it falls when
        # Windows or the firmware slows the processor to cool it). Read through the WMI class,
        # whose names are never translated (#21).
        out = winproc.run(["powershell", "-NoProfile", "-Command",
                           "$p = (Get-CimInstance Win32_PerfFormattedData_Counters_ProcessorInformation -Filter \"Name='_Total'\" "
                           "-ErrorAction SilentlyContinue).PercentProcessorPerformance; "
                           "[string]::Format([Globalization.CultureInfo]::InvariantCulture, '{0:F0}', $p)"],
                          capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW, timeout=20).stdout.strip()
        try:
            row["cpu_speed"] = float(out) or None
        except ValueError:
            pass
        return row

    def _heat_loop(self):
        while not self._stop.wait(4.0):
            try:
                self.heat.append(self._heat_sample())
            except Exception:
                pass

    def _windows_load(self):
        """Task Manager's GPU %: the busiest process's 3D engine use, from Windows' counter."""
        return self._sample(nvidia=False)[1]

    def _load_loop(self, interval):
        while not self._stop.wait(interval):
            try:
                util = self._windows_load()
                if util is not None:
                    self.samples.append((time.time(), util))
            except Exception:
                pass

    def _loop(self, interval):
        while not self._stop.wait(interval):
            try:
                mem, util = self._sample()
                self.peak_mb = max(self.peak_mb, mem)
                if util is not None:
                    self.util.append(util)
                    if not self._load_thread:
                        self.samples.append((time.time(), util))
            except Exception:
                pass

    def busy_between(self, t0: float, t1: float) -> int | None:
        """Average graphics card load (%) while a scene was timed; None with too few samples.
        The scene's times are whole seconds, so the window is widened by one second."""
        vals = [u for t, u in self.samples if t0 <= t <= t1 + 1]
        return round(sum(vals) / len(vals)) if len(vals) >= 3 else None

    def __enter__(self):
        self._thread.start()
        if self._load_thread:
            self._load_thread.start()
        if self._heat_thread:
            self._heat_thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=15)
        if self._load_thread:
            self._load_thread.join(timeout=25)
        if self._heat_thread:
            self._heat_thread.join(timeout=25)


UNCAPPED_FPS = 300        # DCS's own highest frame-rate limit


def fps_cap(goal_fps) -> int:
    """The frame-rate limit a test runs under: twice the frame rate the player is aiming for, and at
    least 120. A test used to run with no limit at all, which drives a fast graphics card far harder
    than flying does (a player lost their picture in #32, and the test PC's driver reset once on
    2026-11-18). Twice the goal keeps the room the measurement needs: a PC that reaches the limit has
    double what it was asked for."""
    try:
        goal = float(goal_fps)
    except (TypeError, ValueError):
        return UNCAPPED_FPS
    return int(min(UNCAPPED_FPS, max(120, round(goal * 2))))


GRAPHICS_RESET = (
    "The graphics driver stopped and Windows restarted it during the test, so DCS could not go on. Your "
    "settings have been put back. This is not caused by a DCS setting: it happens when the graphics card or "
    "its driver gives up under full load. Things that help: remove any overclock or undervolt of the graphics "
    "card, install the current graphics driver (a clean install), check the card's temperature and its power "
    "cables, then try again. If it keeps happening only in this test, please tell us.")
BUSY_GPU_PERCENT = 25     # refuse to test above this while DCS is not even running
# In VR the headset software (Mixed Reality portal, SteamVR, Virtual Desktop, Link, Pimax Play) draws
# its home screen until DCS takes over the headset; a VR tester saw 38% from that alone. Only a
# game or a render running at the same time pushes the card near full load.
VR_BUSY_GPU_PERCENT = 85


def busy_limit(vr: bool = False) -> int:
    """How busy the graphics card may be before DCS starts without the test refusing to run."""
    return VR_BUSY_GPU_PERCENT if vr else BUSY_GPU_PERCENT
# Video memory in use before DCS starts. A desktop with a browser and two 4K monitors sits near
# 2 GB; more than this means another program (a game, an AI tool, a video editor) is holding it.
OTHER_VRAM_MB, OTHER_VRAM_SHARE = 2500, 0.20
# In VR the headset's own software is running before DCS starts and holds video memory too
# (SteamVR with a 2880 x 2880 headset: about 1.5 GB). It is part of playing in VR, not "another program".
VR_SOFTWARE_VRAM_MB = 2000


def other_vram_high(other_mb: float, total_mb: float = 0, vr: bool = False) -> bool:
    """True when other programs hold enough video memory to distort what the test measures."""
    return other_mb > max(OTHER_VRAM_MB, OTHER_VRAM_SHARE * (total_mb or 0)) + (VR_SOFTWARE_VRAM_MB if vr else 0)


VR_STARTED = "OpenXR: Creating swapchain for view"      # DCS writes this once the headset accepted a picture
VR_FAILED = ("OpenXR failure", "OpenXR exception")


def vr_started(dcs_log: str) -> bool:
    """Did DCS really render to the headset? When the headset software reports no headset, DCS
    carries on and draws on the monitor without saying so - those would be monitor numbers."""
    return VR_STARTED in dcs_log and not any(bad in dcs_log for bad in VR_FAILED)


# The headset software's own processes (home screens, compositors, streamers). In VR their load is
# expected before DCS starts and is left out of the "another program is using the card" check: Pimax
# Home on a Crystal Light at 90 Hz alone kept an RTX 4080 87% busy on the test PC (2026-11-20).
HEADSET_PROCESS = re.compile(
    r"^(PimaxHome.*|PimaxClient|pi_server|pi_overlay|pi_vst|pvrhome.*|DevicesSetting|"
    r"vrserver|vrcompositor|vrmonitor|vrdashboard|vrwebhelper|steamtours|"
    r"MixedRealityPortal|MixedRealityPortal\.Brokered|SpatialAudioLicenseSrv|"
    r"OVRServer_x64|OVRRedir|OculusClient|OculusDash|"
    r"VirtualDesktop\..*|PicoConnect.*|Streaming Assistant|"
    r"VarjoHome|VarjoCompositor|BigscreenBeyond.*)$", re.I)


def parse_process_loads(text: str) -> list[tuple[str, float]]:
    """Lines "name;load" from vr_process_loads' PowerShell into (name, load %) pairs."""
    out = []
    for line in (text or "").splitlines():
        name, _, load = line.strip().rpartition(";")
        try:
            out.append((name, float(load.replace(",", "."))))
        except ValueError:
            pass
    return out


def other_load(loads: list[tuple[str, float]]) -> float:
    """The busiest program that is not the headset software, in %."""
    return max((u for n, u in loads if not HEADSET_PROCESS.match(n or "")), default=0.0)


def vr_process_loads() -> list[tuple[str, float]]:
    """Graphics card 3D load per program right now, from Windows' own counters (the WMI class,
    whose names are never translated, #21)."""
    out = winproc.run(["powershell", "-NoProfile", "-Command",
                          "Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine -ErrorAction SilentlyContinue | "
                          "? Name -like '*engtype_3D' | Group-Object { ($_.Name -split '_')[1] } | % { "
                          "$p = Get-Process -Id ([int]$_.Name) -ErrorAction SilentlyContinue; "
                          "[string]::Format([Globalization.CultureInfo]::InvariantCulture, '{0};{1:F1}', "
                          "$(if ($p) { $p.ProcessName } else { '?' }), ($_.Group | Measure-Object UtilizationPercentage -Sum).Sum) }"],
                         capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW, timeout=30).stdout
    return parse_process_loads(out)


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
                 timeout: int = 600, log=print, vr: bool = False, vram_total_mb: float = 0, scene=None,
                 busy: bool = False):
        self.scene = scene                 # the player's map and aircraft (issue #23); None = the default test
        self.busy = bool(busy)             # add the busy-airfield scene (issues #23, #35)
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
        self.vram_total_mb = vram_total_mb or 0       # the card's size, to judge other_vram_mb against
        self.keep_raw_dir = None      # developer aid: keep every frame time

    # -- session lifecycle ---------------------------------------------------
    def __enter__(self):
        if dcs_running():
            raise BenchError("DCS is running. Close it first; DCS Graphics Optimizer never touches a running game.")
        if self.vr and pimax_home_running():
            raise BenchError(PIMAX_HOME_RUNNING)
        load, self.other_vram_mb = gpu_idle_check()
        if self.vr and load > BUSY_GPU_PERCENT:
            # Most of that is usually the headset software's home screen: judge only the other programs.
            try:
                per = [vr_process_loads() for _ in range(3)]
                if any(per):
                    head = max((u for p in per for n, u in p if HEADSET_PROCESS.match(n or "")), default=0.0)
                    others = sum(other_load(p) for p in per) / len(per)
                    self.log(f"The graphics card is {load:.0f}% busy before DCS starts; the headset software's own "
                             f"screen accounts for about {head:.0f}% and other programs for {others:.0f}%.")
                    load = others
            except Exception:
                pass
        limit = busy_limit(self.vr)
        if load > limit and not self.allow_busy:
            raise BenchError(f"Another program is using your graphics card ({load:.0f}% busy before DCS has even "
                             "started). Close games, video renders, AI tools and browser videos, then try again; "
                             "otherwise the results would be wrong.")
        if load > limit:
            self.log(f"WARNING: graphics card is {load:.0f}% busy before DCS starts; results will be unreliable.")
        elif self.vr and load > BUSY_GPU_PERCENT:
            self.log(f"The graphics card is {load:.0f}% busy before DCS starts, most likely the headset software's "
                     "home screen. That's expected in VR; DCS takes over the headset when it starts.")
        if other_vram_high(self.other_vram_mb, self.vram_total_mb, self.vr):
            of = f" of {self.vram_total_mb / 1024:.0f} GB" if self.vram_total_mb else ""
            self.log(f"WARNING: other programs are using {self.other_vram_mb / 1024:.1f} GB{of} of video memory "
                     "before DCS starts. The test continues, but the video memory figures will include them and "
                     "the recommendation may be more cautious than needed. Close them and test again for the best result.")
        self.session.begin()
        self._cleaned = self._stopped = False
        with _open_lock:
            _open_benches.add(self)
        self.hook_dst.parent.mkdir(parents=True, exist_ok=True)
        self.mission_dst.parent.mkdir(parents=True, exist_ok=True)
        self._install_hook()
        from . import scenes
        self.busy = self.busy and scenes.busy_ok(self.scene)
        if self.busy and not getattr(self, "_busy_time_added", False):
            self.timeout += 60                 # the fourth scene and its 160 units need about half a minute more
            self._busy_time_added = True
        self.scene_used = scenes.write_mission(self.scene, self.mission_dst, self.busy)
        return self

    def _install_hook(self):
        """A fresh copy of the hook with a new key. Done before every DCS start: the hook deletes
        itself as soon as DCS loads it, so a key is on disk only until DCS has read it, and the
        hook obeys only a directive that carries that key."""
        self.key = secrets.token_hex(16)
        hook = HOOK_SRC.read_text(encoding="utf-8")
        if hook.count(KEY_MARK) != 1:
            raise BenchError("The benchmark script inside this program is damaged.")
        self.hook_dst.write_text(hook.replace(KEY_MARK, self.key), encoding="utf-8", newline="")

    def __exit__(self, *exc):
        self.cleanup()
        return False

    def _state_lock(self) -> threading.Lock:
        lock = self.__dict__.get("_lock")
        if lock is None:
            lock = self.__dict__.setdefault("_lock", threading.Lock())
        return lock

    def abort(self):
        """The program is closing mid-test: close the DCS this test started (so it cannot save the trial
        settings when it exits), then put everything back. A DCS that Steam started instead is left alone."""
        with self._state_lock():
            proc, self._stopped = getattr(self, "_proc", None), True
        if proc is not None and proc.poll() is None:
            self.log("The optimizer is closing during a test: closing the DCS it started.")
            try:
                proc.kill()
                proc.wait(timeout=30)
            except Exception:
                pass
        self.cleanup()

    def cleanup(self):
        """Put the player's files back. Runs at the end of every test, and again if the program closes
        mid-test; only the first call does anything."""
        with self._state_lock():
            if getattr(self, "_cleaned", False):
                return
            self._cleaned = self._stopped = True
            with _open_lock:
                _open_benches.discard(self)
            self._cleanup()

    def _cleanup(self):
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
        from .optimize import summarize
        self.runs += 1
        tag = f"{self.session_id}r{self.runs:02d}"
        raw, gpu, seconds = self._launch(changes, {"tag": tag}, short, self.timeout)
        result = parse_result(raw)
        for sc in result["scenes"]:
            w0, w1 = sc.pop("w0", None), sc.pop("w1", None)
            if w0 and w1:
                sc["gpu_busy"] = gpu.busy_between(w0, w1)
        result["vram_peak_mb"] = round(gpu.peak_mb) or None
        result["vram_other_mb"] = round(self.other_vram_mb)      # already in use before DCS started
        result["gpu_util_avg"] = round(sum(gpu.util) / len(gpu.util)) if gpu.util else None
        result["seconds"] = seconds
        result["changes"] = changes
        s = summarize(result)
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
        for t in trials:      # the hook applies these inside DCS; DCS may save them on exit
            self.session.note_values({"graphics." + k: v for k, v in t.get("set", {}).items()})
        named = [dict(t, tag=f"{self.session_id}r{self.runs:02d}{t['tag']}") for t in trials]
        raw, gpu, seconds = self._launch(None, {"tag": named[0]["tag"], "trials": named,
                                                "screenshots": screenshots}, short, 330 + 100 * len(trials))
        if not raw.get("ok"):
            raise BenchError("benchmark did not finish: " + (raw.get("reason") or "unknown"))
        out = []
        for t, src in zip(raw["trials"], trials):
            scenes = [dict(frame_stats([float(x) for x in sc["frame_ms"]]), name=sc["name"]) for sc in t["scenes"]]
            out.append({"tag": src["tag"], "applied": t["applied"], "scenes": scenes,
                        "avg_fps": round(sum(sc["avg_fps"] for sc in scenes) / len(scenes), 2)})
        self.log(f"  {len(out)} trials in {seconds}s, VRAM peak {round(gpu.peak_mb)} MB")
        return out

    def soak(self, laps: int = 6) -> dict:
        """The heat check (#23): the same scenes flown `laps` times in ONE DCS session with the
        player's own settings, full-length scenes, while temperatures and clocks are sampled.
        Returns {"laps": [{"avg_fps", "p1_low_fps", "t0", "t1"}], "samples": [...], "seconds"}.
        A first lap is flown and thrown away: it absorbs texture loading."""
        self.runs += 1
        trials = [{"tag": "warm", "set": {}, "settle_sec": self.settle_sec}]
        trials += [{"tag": f"h{n:02d}", "set": {}, "settle_sec": BATCH_SETTLE_SEC} for n in range(laps)]
        named = [dict(t, tag=f"{self.session_id}r{self.runs:02d}{t['tag']}") for t in trials]
        self._heat = True
        try:
            raw, gpu, seconds = self._launch(None, {"tag": named[0]["tag"], "trials": named, "screenshots": False},
                                             False, 420 + 150 * len(trials))
        finally:
            self._heat = False
        if not raw.get("ok"):
            raise BenchError("benchmark did not finish: " + (raw.get("reason") or "unknown"))
        out = []
        for t in raw["trials"][1:]:
            stats = [frame_stats([float(x) for x in sc["frame_ms"]]) for sc in t["scenes"]]
            w0 = [sc.get("w0") for sc in t["scenes"] if sc.get("w0")]
            w1 = [sc.get("w1") for sc in t["scenes"] if sc.get("w1")]
            out.append({"avg_fps": sum(s["avg_fps"] for s in stats) / len(stats),
                        "p1_low_fps": min(s["p1_low_fps"] for s in stats),
                        "t0": min(w0) if w0 else 0, "t1": max(w1) if w1 else 0})
            self.log(f"  lap {len(out)}: avg {out[-1]['avg_fps']:.0f} FPS, 1% low {out[-1]['p1_low_fps']:.0f} FPS")
        return {"laps": out, "samples": gpu.heat, "seconds": seconds}

    def _steam_restart(self) -> bool:
        """True when the DCS that just closed handed its start over to Steam. Steam then asks
        the player to OK the launch options before it starts DCS again (#27)."""
        try:
            head = (self.profile_dir / "Logs" / "dcs.log").read_text(encoding="utf-8", errors="ignore")[:20000]
        except OSError:
            return False
        return STEAM_RESTART in head

    def _follow_handoff(self, deadline: float, wait: float = HANDOFF_WAIT_SEC) -> bool:
        """DCS.exe can close at once because something else starts it again (Steam, the DCS
        updater). If a DCS appears within a while, wait for that one instead of starting
        a second copy. True if one was followed to the end (#17, #27)."""
        seen = None
        until = time.time() + wait
        while True:
            if dcs_running():
                seen = time.time()
                break
            if time.time() >= until:
                break
            time.sleep(2)
        if not seen:
            return False
        self.log("  DCS was started again by another program (for example Steam); following that one...")
        done_at = None
        while dcs_running():
            if self.result.exists():
                done_at = done_at or time.time()
                if time.time() - done_at > EXIT_GRACE_SEC:         # finished but did not close: close it
                    self.log("  The benchmark finished but DCS did not close by itself; closing it.")
                    _taskkill_dcs()
                    time.sleep(5)
                    return True
            elif time.time() > deadline and not self._still_working(deadline):
                self.directive.unlink(missing_ok=True)
                self._keep_failure_log()
                raise BenchError("DCS did not finish the benchmark in time. Close DCS, then try again.")
            time.sleep(2)
        return True

    def _log_tail(self, size: int = 200_000) -> bytes | None:
        """The end of dcs.log, or None when there is none yet from the DCS this test started."""
        try:
            log = self.profile_dir / "Logs" / "dcs.log"
            if log.stat().st_mtime < getattr(self, "_launched_at", 0):
                return None                     # still the log of an earlier DCS start
            with open(log, "rb") as f:
                f.seek(max(0, log.stat().st_size - size))
                return f.read()
        except OSError:
            return None

    def _crashed(self) -> bool:
        """Did the DCS this test started crash? DCS then writes a crash report and may sit behind a
        crash box that nobody is there to click (issue #58)."""
        return CRASH_MARK in (self._log_tail() or b"")

    def _check_runtime(self) -> None:
        """Warn once if DCS's module list shows the Visual C++ runtime from our _MEI folder (issue #58)."""
        if getattr(self, "_runtime_warned", False):
            return
        tail = self._log_tail(2_000_000)
        if tail and winproc.bundled_runtime_lines(tail.decode("utf-8", errors="ignore")):
            self._runtime_warned = True
            self.log(winproc.BUNDLED_RUNTIME_WARNING)

    def _stop_after_crash(self, proc) -> None:
        """DCS crashed: close it, put the player's settings back now, and stop the test."""
        tail = self._log_tail(2_000_000) or b""
        try:
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=30)
        except Exception:
            pass
        self.directive.unlink(missing_ok=True)
        self._keep_failure_log()
        self._check_runtime()
        self.session.end()                      # at once, not when the test winds down
        raise DcsCrashed(crash_message(during_startup=b"DCSTUNE" not in tail))

    def _graphics_reset(self) -> bool:
        """Did Windows reset the graphics driver under DCS? DCS then writes 'DX device removed' and
        stops with a crash box that nobody is there to click, so the test used to wait ten minutes
        and blame a slow start (seen on the test PC on 2026-11-18: an RTX 4080 driver reset in the
        cloud scene over Nevada)."""
        tail = self._log_tail()
        if tail is None:
            return False
        return b"DX device removed" in tail or b"DXGI_ERROR_DEVICE_REMOVED" in tail or b"DXGI_ERROR_DEVICE_HUNG" in tail

    def _wait_for(self, proc, deadline: float) -> bool:
        """Wait for the DCS we started. True when it closed, or when the benchmark finished and
        DCS was closed for it because it stayed open (beta 15 logs: result written, then DCS sat
        at the menu and the test was wrongly called a failure). False on a real timeout."""
        done_at, looked = None, time.time()
        while True:
            try:
                proc.wait(timeout=2)
                return True
            except subprocess.TimeoutExpired:
                pass
            if not self.result.exists() and time.time() - looked > 10:
                looked = time.time()
                if self._crashed():
                    self._stop_after_crash(proc)
                if self._graphics_reset():
                    proc.kill()
                    proc.wait(timeout=30)
                    self.directive.unlink(missing_ok=True)
                    self._keep_failure_log()
                    raise BenchError(GRAPHICS_RESET)
            if self.result.exists():
                done_at = done_at or time.time()
                if time.time() - done_at > EXIT_GRACE_SEC:
                    self.log("  The benchmark finished but DCS did not close by itself; closing it.")
                    proc.kill()
                    proc.wait(timeout=30)
                    return True
            elif time.time() > deadline and not self._still_working(deadline):
                proc.kill()
                proc.wait(timeout=30)
                return False

    def _still_working(self, deadline: float) -> bool:
        """Past the deadline: is DCS still writing to its log (busy, not stuck), within the extra time?"""
        if time.time() > deadline + BUSY_EXTRA_SEC:
            return False
        try:
            active = time.time() - (self.profile_dir / "Logs" / "dcs.log").stat().st_mtime < LOG_ACTIVE_SEC
        except OSError:
            return False
        if active and not getattr(self, "_busy_noted", False):
            self._busy_noted = True
            self.log("  DCS is taking longer than usual but is still working (an add-on may be doing "
                     "one-time setup); waiting a bit more...")
        return active

    def _keep_failure_log(self):
        try:
            shutil.copyfile(self.profile_dir / "Logs" / "dcs.log",
                            self.profile_dir / "Config" / "dcstune-last-failure.log")
        except OSError:
            pass

    def _launch(self, changes, directive_extra: dict, short: bool, timeout: int):
        # Trials never change resolution, monitor layout or VR; vsync and the frame
        # cap are lifted for every run (including the baseline) so numbers compare.
        trial = {"graphics.sync": False, "graphics.maxFPS": int(getattr(self, "fps_cap", 0) or UNCAPPED_FPS)}
        trial.update(changes or {})
        if getattr(self, "_stopped", False):        # the program is closing (stop_open_tests)
            raise BenchError("The test was stopped.")
        self.session.write_trial(trial)
        self.result.unlink(missing_ok=True)

        def directive() -> str:
            # New for every DCS start: a fresh hook with its own key, a short validity, and the
            # password and port of the local session DCS has to host to run the mission.
            self._install_hook()
            return json.dumps(dict({
                "key": self.key, "not_after": int(time.time()) + DIRECTIVE_VALID_SEC,
                "password": secrets.token_hex(16), "port": free_port(),
                "mission": str(self.mission_dst), "scenes": SCENES + ([BUSY_SCENE] if self.busy else []),
                "scene_sec": SHORT_SCENE_SEC if short else self.scene_sec,
                "scene_lead_sec": SHORT_LEAD_SEC if short else 4, "settle_sec": self.settle_sec,
                "total_timeout": timeout - 30},
                # development only: force the fallback way of finding the aircraft (issue #3)
                **({"subject_source": os.environ["DCSTUNE_SUBJECT_SOURCE"]}
                   if os.environ.get("DCSTUNE_SUBJECT_SOURCE") in ("server", "direct") else {}),
                **directive_extra))
        self.directive.write_text(directive())
        if winproc.prefer_system32_on():
            self.directive.unlink(missing_ok=True)
            raise BenchError(winproc.ADVICE)
        args = [str(self.exe), "--no-launcher", "--force_enable_VR" if self.vr else "--force_disable_VR",
                "-w", self.profile_name]
        popen_extra = {}
        if is_steam_exe(self.exe):
            if not steam_running():
                self.directive.unlink(missing_ok=True)
                raise BenchError("This is the Steam edition of DCS, and Steam is not open. Open Steam and "
                                 "sign in (tick \"Remember me\"), then try again.")
            popen_extra = {"env": steam_launch_env()}
        started = time.time()
        for attempt in (1, 2):
            if attempt == 2:
                self.log("  DCS closed straight away; waiting a moment and starting it again...")
                time.sleep(15)
                late = dcs_running()            # a DCS came up late (Steam, after the player clicked)
                if not late:                    # its hook may already be reading the current directive
                    self.directive.write_text(directive())
            launched = self._launched_at = time.time()
            with GpuSampler(heat=getattr(self, "_heat", False)) as gpu:
                if attempt == 2 and late:
                    # never start a second DCS next to one that is already coming up (#27)
                    quick = not self._follow_handoff(launched + timeout, wait=0)
                else:
                    try:
                        with self._state_lock():     # never start DCS after the program began closing
                            if getattr(self, "_stopped", False):
                                self.directive.unlink(missing_ok=True)
                                raise BenchError("The test was stopped.")
                            proc = self._proc = winproc.popen(args, cwd=str(self.exe.parent), **popen_extra)
                    except OSError as e:
                        self.directive.unlink(missing_ok=True)
                        if getattr(e, "winerror", None) == 740:
                            # Windows error 740, "requires elevation" (beta issue #44): DCS.exe is set
                            # to always run as administrator, and this program was started normally.
                            raise BenchError(NEEDS_ADMIN) from e
                        raise
                    if not self._wait_for(proc, launched + timeout):
                        self.directive.unlink(missing_ok=True)
                        self._keep_failure_log()
                        raise BenchError("DCS did not finish the benchmark in time and was closed. "
                                         "Check that DCS starts normally and is logged in.")
                    if not self.result.exists() and self._crashed():
                        self._stop_after_crash(None)    # it crashed and closed: no restart, no retry
                    quick = not self.result.exists() and time.time() - launched <= QUICK_EXIT_SEC
                if quick:
                    wait = HANDOFF_WAIT_SEC
                    if self._steam_restart():
                        wait = STEAM_PROMPT_WAIT_SEC
                        self.log("  Steam is starting DCS. If Steam asks about launch options, click Continue "
                                 "(the test needs them); the test waits for you.")
                    if self._follow_handoff(launched + timeout + wait, wait=wait):
                        quick = False
            if not quick:
                break
            if attempt == 2:
                self.directive.unlink(missing_ok=True)
                self._keep_failure_log()
                raise DcsWontStart(
                    "DCS closed straight away twice when this tool started it, so the test was stopped. "
                    "Start DCS once yourself and check it reaches the main menu without asking anything "
                    "(log-in, update, or a message to click), close it, then try again. If you start DCS "
                    "through Steam, start it once from Steam first.")
        time.sleep(3)      # let DCS finish releasing its files before anything else starts
        self._check_runtime()
        if not self.result.exists():
            self.directive.unlink(missing_ok=True)
            self._keep_failure_log()
            raise BenchError("DCS closed without writing a benchmark result "
                             "(a copy of its log is in Config\\dcstune-last-failure.log).")
        if self.vr:
            try:
                dcs_log = (self.profile_dir / "Logs" / "dcs.log").read_text(encoding="utf-8", errors="ignore")
            except OSError:
                dcs_log = ""
            if not vr_started(dcs_log):
                self.directive.unlink(missing_ok=True)
                self.result.unlink(missing_ok=True)
                self._keep_failure_log()
                raise BenchError("DCS could not show its picture in the headset, so it ran on the monitor instead. "
                                 "Nothing was measured. Check that the headset is connected, switched on and "
                                 "working in its own software, then try again.")
        raw_text = self.result.read_text()
        try:
            if not json.loads(raw_text).get("ok"):
                self._keep_failure_log()          # the hook gave up: its reasons are in DCS's log
        except ValueError:
            self._keep_failure_log()
        if self.keep_raw_dir:
            (Path(self.keep_raw_dir) / f"dcstune-raw-{time.strftime('%H%M%S')}-{directive_extra['tag']}.json").write_text(raw_text)
        return json.loads(raw_text), gpu, round(time.time() - started)
