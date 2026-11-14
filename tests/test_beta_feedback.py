"""Fixes for problems players reported on beta 11 (GitHub issues #6, #7, #8, #1)."""
import subprocess

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
