"""Fixes for problems players reported on beta 11 (GitHub issues #6, #7, #8, #1)."""
import subprocess
import pytest

from dcstune import bench, rate, sysinfo, winproc
from dcstune.optionslua import Options
from test_core import FIX, INFO


def test_laptop_rtx_is_rated_not_the_builtin_graphics_that_drives_the_screen():
    # Issue #6: on a gaming laptop the built-in chip drives the screen; the RTX card renders.
    raw = {"gpus": [
        {"name": "AMD Radeon(TM) 610M", "vram_mb": 512, "width": 2560, "height": 1600, "refresh": 240},
        {"name": "NVIDIA GeForce RTX 4090 Laptop GPU", "vram_mb": 16376},
        {"name": "Microsoft Basic Display Adapter", "vram_mb": 0}],
        "display": {"width": 2560, "height": 1600, "refresh": 240, "count": 1}}
    g = sysinfo.normalize(raw)["gpu"]
    assert g["name"].endswith("Laptop GPU") and g["vram_mb"] == 16376
    assert (g["width"], g["height"], g["refresh"]) == (2560, 1600, 240)
    m = rate.rate_machine(dict(INFO, gpu=g))
    assert 60 <= m["gpu_score"] < 92          # a laptop 4090 is not a desktop 4090, nor an iGPU
    # No display answer from Windows: the screen's figures still come from the chip that drives it.
    g = sysinfo.normalize(dict(raw, display=None))["gpu"]
    assert g["name"].endswith("Laptop GPU") and g["width"] == 2560


def test_desktop_card_still_wins_over_an_idle_integrated_chip():
    raw = {"gpus": [{"name": "Intel(R) UHD Graphics 770", "vram_mb": 128},
                    {"name": "NVIDIA GeForce RTX 4080", "vram_mb": 16376, "width": 3840, "height": 2160, "refresh": 60}]}
    assert sysinfo.normalize(raw)["gpu"]["name"] == "NVIDIA GeForce RTX 4080"


def _flat(**changes):
    o = rate.flat_options(Options.load(FIX / "options.DCS.lua"))
    o.update(changes)
    return o


def test_picture_spanning_exported_screens_is_not_called_a_mistake():
    # Issue #7: 2560x2880 on a 1440p projector because the MFDs are exported to a second screen.
    info = dict(INFO, gpu=dict(INFO["gpu"], width=2560, height=1440, refresh=60))
    machine = rate.rate_machine(info)
    texts = lambda fit: " ".join(f["text"] for f in fit["findings"])
    mistake = rate.rate_settings(info, _flat(**{"graphics.width": 2560, "graphics.height": 2880}), machine)
    assert "thrown away" in texts(mistake)
    for extra in ({"graphics.multiMonitorSetup": "MFD_export"}, {}):
        i = dict(info, display={"width": 2560, "height": 1440, "count": 2}) if not extra else info
        fit = rate.rate_settings(i, _flat(**{"graphics.width": 2560, "graphics.height": 2880}, **extra), machine)
        assert "thrown away" not in texts(fit) and "kept exactly as they are" in texts(fit)
        assert fit["score"] > mistake["score"]


def test_unreadable_tasklist_output_does_not_crash(monkeypatch):
    # Issue #8: "argument of type 'NoneType' is not iterable" - on a non-English Windows the
    # decoded tasklist text could come back as None.
    class R:
        stdout = None
    monkeypatch.setattr(bench.subprocess, "run", lambda *a, **k: R())
    assert bench.dcs_running() is False


def test_hardware_reading_survives_bytes_the_code_page_cannot_decode(monkeypatch):
    out = ('{"cpu":"Ryzen @@","gpus":[],"installs":[],"profiles":[{"name":"DCS","path":"C:\\\\Users\\\\Jos\u00e9\\\\Saved Games\\\\DCS",'
           '"options":"x","modified":"2026-11-13T00:00:00"}]}').encode("utf-8")

    class P:
        stdout, stderr = b"\xef\xbb\xbf" + out.replace(b"@@", b"\x81"), b""      # a byte no code page decodes
    monkeypatch.setattr(sysinfo.subprocess, "run", lambda *a, **k: P())
    monkeypatch.setattr(sysinfo, "primary_display", lambda: None)
    info = sysinfo.collect()
    assert info["profiles"][0]["path"].endswith("Jos\u00e9\\Saved Games\\DCS")


def test_gpu_counter_with_comma_decimals_is_read(monkeypatch):
    monkeypatch.setenv("DCSTUNE_NO_NVSMI", "1")
    s = bench.GpuSampler()

    class R:
        stdout = "8112;45.3\n"
    monkeypatch.setattr(bench.subprocess, "run", lambda *a, **k: R())
    assert s._sample() == (8112.0, 45.3)
    R.stdout = "8112,45,3"                      # an old-style, culture-formatted answer: ignored, not a crash
    assert s._sample() == (0.0, None)


def test_browser_policy_blocks_the_dcs_start_with_advice(monkeypatch):
    # Issue #1: started from a Firefox-based browser, DCS would load System32\Input.dll.
    monkeypatch.setattr(winproc, "prefer_system32_on", lambda: True)
    assert "File Explorer" in winproc.ADVICE
    monkeypatch.setattr(winproc.sys, "frozen", True, raising=False)
    started = []
    monkeypatch.setattr(winproc.subprocess, "Popen", lambda args: started.append(args))
    monkeypatch.setattr(winproc, "RESTART_MARK", winproc.Path(subprocess.os.devnull + "-nonexistent-dir/x"))
    assert winproc.restart_through_explorer() is False       # cannot leave its mark: does not restart blind
    assert started == []


def test_restart_through_explorer_happens_once(tmp_path, monkeypatch):
    monkeypatch.setattr(winproc, "prefer_system32_on", lambda: True)
    monkeypatch.setattr(winproc.sys, "frozen", True, raising=False)
    monkeypatch.setattr(winproc, "RESTART_MARK", tmp_path / "mark")
    started = []
    monkeypatch.setattr(winproc.subprocess, "Popen", lambda args: started.append(args))
    assert winproc.restart_through_explorer() is True
    assert started[0][0] == "explorer.exe"
    assert winproc.restart_through_explorer() is False       # just restarted and still on: no loop
    assert len(started) == 1


def test_fast_screen_does_not_strip_a_mid_range_pc(monkeypatch):
    # Issue #12: RX 7700 XT on a fast monitor. The player already runs nice-looking settings
    # smoothly; the tool must not trade most of the picture for a few frames.
    from dcstune import model as M, optimize
    from test_core import FakePC, _current
    hi = dict(_current())
    for s in M.SETTINGS:
        hi[s["key"]] = s["levels"][-2 if len(s["levels"]) > 2 else -1]["v"]
    top = M.max_quality("amd")
    for gpu, cpu in ((44, 62), (60, 75), (78, 100)):
        pc = FakePC(hi, gpu, cpu)
        out = optimize.run(M.Model(gpu, cpu, 2560, 1440, "amd"), hi, "amd", rate.target_fps(144), 12288,
                           pc.measure, log=lambda *_: None)
        rec = out["recommended"]
        after = rec["quality"] if rec else out["current_quality"]
        assert after >= out["current_quality"] - 0.05 * top, (gpu, out["target_fps"])


def _session(tmp_path):
    import shutil
    from dcstune.optionslua import TrialSession
    p = tmp_path / "options.lua"
    shutil.copy(FIX / "options.DCS.lua", p)
    s = TrialSession(p)
    s.begin()
    return p, s


def test_interrupted_test_keeps_settings_the_player_changed_afterwards(tmp_path):
    # Issue #15: a test was stopped, the player changed settings in DCS, and the tool's next
    # start silently put the settings from before the test back over them.
    from dcstune.optionslua import list_backups, recover, sha256
    p, s = _session(tmp_path)
    original = (tmp_path / "options.lua.dcstune-original").read_bytes()
    s.write_trial({"graphics.shadows": 0, "graphics.sync": False})
    s.note_values({"graphics.clouds": 0})               # applied in-game by a batch
    o = Options.load(p)
    o.update({"graphics.clouds": 0, "graphics.visibRange": "Low"})   # visibRange: the player's own change
    o.save(p)
    edited = sha256(p)
    assert recover(p, keep_player_edits=True) == "kept"
    assert sha256(p) == edited
    assert [b.read_bytes() for b in list_backups(p)] == [original]   # Undo goes back to before the test
    assert not (tmp_path / "options.lua.dcstune-original").exists()
    assert recover(p, keep_player_edits=True) is False


def test_interrupted_test_with_only_test_values_is_restored(tmp_path):
    from dcstune.optionslua import list_backups, recover, sha256
    p, s = _session(tmp_path)
    original = sha256(tmp_path / "options.lua.dcstune-original")
    s.write_trial({"graphics.shadows": 0})
    s.note_values({"graphics.clouds": 0})
    o = Options.load(p)
    o.update({"graphics.clouds": 0})                  # DCS saved a batch value on exit: not the player
    o.save(p)
    assert recover(p, keep_player_edits=True) == "restored"
    assert sha256(p) == original and list_backups(p) == []


def test_player_chooses_smoothness_balanced_or_quality():
    # Beta feedback: "gained 60 fps but the graphics was not great" - let the player decide.
    from dcstune import model as M, optimize
    from test_core import FakePC, _current
    cur = _current()
    got = {}
    for mode in ("smooth", "balanced", "quality"):
        pc = FakePC(cur, 78, 100)
        out = optimize.run(M.Model(78, 100, 2560, 1440, "nvidia"), cur, "nvidia", rate.target_fps(144), 16376,
                           pc.measure, log=lambda *_: None, mode=mode)
        rec = out["recommended"]
        got[mode] = (out["target_fps"], rec["quality"] if rec else out["current_quality"])
        assert out["mode"] == mode
    assert got["smooth"][0] >= got["balanced"][0] >= got["quality"][0]
    assert got["smooth"][1] <= got["balanced"][1] <= got["quality"][1]
    assert got["smooth"][0] > got["quality"][0] and got["quality"][1] > got["smooth"][1]
    import pytest
    with pytest.raises(ValueError):
        optimize.run(M.Model(78, 100, 2560, 1440), cur, "nvidia", 120, 16376, FakePC(cur, 78, 100).measure,
                     log=lambda *_: None, mode="ultra")


def test_window_passes_the_choice_and_refuses_unknown_ones():
    import pytest
    from dcstune import ui
    seen = []
    eng = type("E", (), {"info": dict(INFO, installs=[{}]), "sharing": lambda self: {"available": False},
                         "optimize": lambda self, full, log, mode="balanced": seen.append((full, mode)) or {}})()
    app = ui.App(lambda: eng)
    with pytest.raises(RuntimeError, match="Smoothness, Balanced or Quality"):
        app.handle("POST", "/api/optimize", {"full": False, "mode": "ultra"})
    app.handle("POST", "/api/optimize", {"full": True, "mode": "quality"})
    import time
    for _ in range(50):
        if seen:
            break
        time.sleep(0.02)
    assert seen == [(True, "quality")]


def test_dcs_closing_at_once_twice_stops_the_test_instead_of_looping(tmp_path, monkeypatch):
    # Issue #17: "Keeps saying DCS start was interrupted and will start again in a moment... and repeats."
    from dcstune import model as M, optimize
    from test_core import _bench, FakePC, _current
    bench, b = _bench(tmp_path, monkeypatch)
    starts = []

    class Proc:                                   # DCS exits at once and writes nothing
        def __init__(self, args, cwd): starts.append(args)
        def wait(self, timeout=None): return 0
    monkeypatch.setattr(bench.subprocess, "Popen", Proc)
    monkeypatch.setattr(bench.time, "sleep", lambda s: None)
    monkeypatch.setattr(bench, "HANDOFF_WAIT_SEC", 0)
    with b:
        with pytest.raises(bench.DcsWontStart, match="closed straight away twice"):
            b._launch(None, {"tag": "x"}, True, 100)
    assert len(starts) == 2
    # In a thorough test the per-setting "skip and carry on" must not swallow it.
    cur = _current()
    calls = []

    def measure(changes):
        calls.append(changes)
        if len(calls) > 1:
            raise bench.DcsWontStart("x")
        return FakePC(cur, 78, 100).measure(changes)
    with pytest.raises(bench.DcsWontStart):
        optimize.run(M.Model(78, 100, 2560, 1440), cur, "nvidia", 120, 16376, measure, full=True,
                     log=lambda *_: None, measure_fast=measure)
    assert len(calls) == 2


def test_dcs_restarted_by_steam_is_followed_not_started_twice(tmp_path, monkeypatch):
    from test_core import _bench
    bench, b = _bench(tmp_path, monkeypatch)
    starts, running = [], iter([])

    class Proc:                                   # our DCS.exe hands over to a copy Steam starts
        def __init__(self, args, cwd):
            nonlocal running
            starts.append(args)
            running = iter([True, True, True, False])
        def wait(self, timeout=None): return 0
    monkeypatch.setattr(bench.subprocess, "Popen", Proc)
    monkeypatch.setattr(bench.time, "sleep", lambda s: None)

    def dcs_running():
        if not starts:
            return False                          # before the test: no DCS
        alive = next(running, False)
        if not alive:
            b.result.write_text('{"ok":true}')    # the followed DCS finished the benchmark
        return alive
    monkeypatch.setattr(bench, "dcs_running", dcs_running)
    logs = []
    b.log = logs.append
    with b:
        assert b._launch(None, {"tag": "x"}, True, 100)[0] == {"ok": True}
    assert len(starts) == 1 and any("started again by another program" in m for m in logs)


def test_wide_multi_screen_picture_is_graded_against_a_reachable_goal():
    # #7 follow-up: 7920x1440 across three screens (main 3440x1440 at 144 Hz) on an RTX 5080.
    # The score used to demand 120 FPS in the worst moments and called the settings poor.
    info = dict(INFO, gpu=dict(INFO["gpu"], name="NVIDIA GeForce RTX 5080", vram_mb=16303,
                               width=3440, height=1440, refresh=144),
                display={"width": 3440, "height": 1440, "refresh": 144, "count": 3})
    flat = _flat(**{"graphics.width": 7920, "graphics.height": 1440, "graphics.multiMonitorSetup": "MFD_export"})
    fit = rate.rate_settings(info, flat, rate.rate_machine(info))
    assert fit["target_fps"] < 120
    assert "thrown away" not in " ".join(f["text"] for f in fit["findings"])
    # a measured test result keeps using the goal that test aimed for
    assert rate.rate_settings(info, flat, rate.rate_machine(info), {"p1_low_fps": 70, "avg_fps": 90}, 72)["target_fps"] == 72
