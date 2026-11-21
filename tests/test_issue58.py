# DCS Graphics Optimizer - Fox3 Managed Solutions Inc.
# Created 2026-11-21. Tests for GitHub issue #58: DCS started by the packaged app crashed at start-up.
"""Issue #58: DCS loaded the Visual C++ runtime from the packaged app's _MEI folder and crashed while it
started, and closing the optimizer mid-test left the trial settings in options.lua."""
import os
import subprocess

import pytest

from dcstune import winproc
from dcstune.optionslua import TrialSession
from test_core import _bench

MEI = os.path.join(os.sep, "tmp", "_MEI123456")
SYNTHETIC_LOG = "2026-11-21 10:00:00.000 INFO    EDCORE (Main): started\n"


def _frozen(monkeypatch, windows=True):
    monkeypatch.setattr(winproc.sys, "_MEIPASS", MEI, raising=False)
    monkeypatch.setattr(winproc, "IS_WINDOWS", windows)


class FakeKernel32:
    def __init__(self, calls):
        self.calls = calls

    def SetDllDirectoryW(self, path):
        self.calls.append(("SetDllDirectoryW", path))
        return 1


# -- 1. starting programs ---------------------------------------------------------------------------------
def test_clean_env_drops_bootloader_variables_and_the_mei_folder_from_path(monkeypatch):
    _frozen(monkeypatch)
    base = {"_MEIPASS2": MEI, "_PYI_APPLICATION_HOME_DIR": MEI, "_pyi_parent_process_level": "1",
            "_MEIPASS": MEI, "PATH": os.pathsep.join([MEI, os.path.join(MEI, "sub"), "/usr/bin", "/opt/x"]),
            "SteamAppId": "223750", "HOME": "/home/x"}
    env = winproc.clean_env(base)
    assert env == {"PATH": os.pathsep.join(["/usr/bin", "/opt/x"]), "SteamAppId": "223750", "HOME": "/home/x"}
    assert "_MEIPASS2" in base                      # the caller's dict is not changed
    assert "_MEIPASS2" not in winproc.clean_env({"_MEIPASS2": "x"})


def test_popen_is_a_plain_popen_when_not_frozen(monkeypatch):
    monkeypatch.delattr(winproc.sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(winproc, "IS_WINDOWS", True)
    k32 = []
    monkeypatch.setattr(winproc, "_kernel32", lambda: FakeKernel32(k32))
    seen = []
    monkeypatch.setattr(winproc.subprocess, "Popen", lambda args, **kw: seen.append((args, kw)) or "proc")
    monkeypatch.setenv("_MEIPASS2", "left-alone")
    assert winproc.popen(["DCS.exe"], cwd="bin-mt") == "proc"
    assert seen == [(["DCS.exe"], {"cwd": "bin-mt"})] and k32 == []         # no env, no DLL switch
    with winproc.clean_dll_search():
        pass
    assert k32 == []


def test_popen_in_the_packaged_app_starts_with_the_default_dll_search_and_puts_ours_back(monkeypatch):
    _frozen(monkeypatch)
    calls = []
    monkeypatch.setattr(winproc, "_kernel32", lambda: FakeKernel32(calls))

    def fake_popen(args, **kw):
        assert winproc._DLL_LOCK.locked()            # nobody else can switch it back meanwhile
        calls.append(("Popen", args, kw["env"]))
        return "proc"
    monkeypatch.setattr(winproc.subprocess, "Popen", fake_popen)
    monkeypatch.setenv("_MEIPASS2", MEI)
    monkeypatch.setenv("_PYI_ARCHIVE_FILE", "x")
    assert winproc.popen(["DCS.exe"], env={"PATH": MEI, "SteamAppId": "223750", "_MEIPASS2": MEI}) == "proc"
    assert [c[0] for c in calls] == ["SetDllDirectoryW", "Popen", "SetDllDirectoryW"]
    assert calls[0][1] is None and calls[2][1] == MEI
    assert calls[1][2] == {"PATH": "", "SteamAppId": "223750"}
    assert not winproc._DLL_LOCK.locked()


def test_the_dll_folder_is_put_back_when_the_start_fails(monkeypatch):
    _frozen(monkeypatch)
    calls = []
    monkeypatch.setattr(winproc, "_kernel32", lambda: FakeKernel32(calls))

    def refuse(args, **kw):
        raise OSError(740, "requires elevation")
    monkeypatch.setattr(winproc.subprocess, "Popen", refuse)
    with pytest.raises(OSError):
        winproc.popen(["DCS.exe"])
    assert calls == [("SetDllDirectoryW", None), ("SetDllDirectoryW", MEI)] and not winproc._DLL_LOCK.locked()


def test_no_dll_switch_off_windows_even_when_frozen(monkeypatch):
    _frozen(monkeypatch, windows=False)
    calls = []
    monkeypatch.setattr(winproc, "_kernel32", lambda: FakeKernel32(calls))
    monkeypatch.setattr(winproc.subprocess, "Popen", lambda args, **kw: "proc")
    assert winproc.popen(["x"]) == "proc" and calls == []


def test_run_in_the_packaged_app_returns_what_subprocess_run_would(monkeypatch):
    _frozen(monkeypatch, windows=False)              # real child process, Linux host
    out = winproc.run(["python3", "-c", "import os; print(os.environ.get('_MEIPASS2', 'clean'))"],
                      capture_output=True, text=True, timeout=30, env=dict(os.environ, _MEIPASS2=MEI))
    assert out.returncode == 0 and out.stdout.strip() == "clean"
    with pytest.raises(subprocess.CalledProcessError):
        winproc.run(["python3", "-c", "raise SystemExit(3)"], check=True)


def test_every_program_start_goes_through_the_helper():
    # A new subprocess.Popen/run elsewhere would bring #58 back for that program.
    import pathlib
    src = pathlib.Path(winproc.__file__).parent
    for f in src.glob("*.py"):
        if f.name == "winproc.py":
            continue
        text = f.read_text(encoding="utf-8")
        assert "subprocess.Popen(" not in text and "subprocess.run(" not in text, f.name


def test_dcs_is_started_through_the_helper(tmp_path, monkeypatch):
    bench, b = _bench(tmp_path, monkeypatch)
    used = []
    real = winproc.popen
    monkeypatch.setattr(winproc, "popen", lambda args, **kw: used.append(args) or real(args, **kw))

    class Proc:
        def __init__(self, args, cwd): pass
        def wait(self, timeout=None): b.result.write_text('{"ok":true}')
        def poll(self): return 0
    monkeypatch.setattr(bench.subprocess, "Popen", Proc)
    monkeypatch.setattr(bench.time, "sleep", lambda s: None)
    with b:
        b._launch(None, {"tag": "x"}, True, 100)
    assert used and used[0][0].endswith("DCS.exe")


# -- 2. the dcs.log check ------------------------------------------------------------------------------
def test_runtime_from_the_mei_folder_is_named_in_a_warning(tmp_path, monkeypatch):
    lines = ["# C:\\Users\\someone\\AppData\\Local\\Temp\\_MEI99999\\VCRUNTIME140.dll",
             "# C:\\Windows\\System32\\MSVCP140.dll", "# C:\\Windows\\System32\\VCRUNTIME140_1.dll"]
    assert winproc.bundled_runtime_lines("\n".join(lines)) == [lines[0]]
    bench, b = _bench(tmp_path, monkeypatch)
    logs = []
    b.log = logs.append
    (tmp_path / "Logs").mkdir()
    (tmp_path / "Logs" / "dcs.log").write_text(SYNTHETIC_LOG + "\n".join(lines))
    b._check_runtime()
    b._check_runtime()
    assert logs == [winproc.BUNDLED_RUNTIME_WARNING] and "#58" in logs[0]
    (tmp_path / "Logs" / "dcs.log").write_text(SYNTHETIC_LOG + lines[1])
    b._runtime_warned = False
    logs.clear()
    b._check_runtime()
    assert logs == []


# -- 3. putting options.lua back ----------------------------------------------------------------------------
def _trial_values_in(b) -> bool:
    return b"maxFPS\"] = 300" in b.options.read_bytes()


def test_restore_is_idempotent(tmp_path, monkeypatch):
    bench, b = _bench(tmp_path, monkeypatch)
    original = b.options.read_bytes()
    with b:
        b.session.write_trial({"graphics.maxFPS": 300})
        assert _trial_values_in(b)
        b.cleanup()
        assert b.options.read_bytes() == original
        b.cleanup()
        b.session.end()
        b.abort()
    assert b.options.read_bytes() == original
    s = TrialSession(b.options)
    s.begin()
    s.end()
    s.end()                                          # a second end finds nothing to do
    assert b.options.read_bytes() == original


def test_closing_the_window_mid_test_puts_the_settings_back_and_closes_our_dcs(tmp_path, monkeypatch):
    bench, b = _bench(tmp_path, monkeypatch)
    original = b.options.read_bytes()

    class Proc:
        killed = False
        def poll(self): return 0 if self.killed else None
        def kill(self): self.killed = True
        def wait(self, timeout=None): return 0
    b.__enter__()
    b.session.write_trial({"graphics.maxFPS": 300})
    b._proc = proc = Proc()
    assert b in bench._open_benches
    assert bench.stop_open_tests("window") >= 1      # pywebview passes the window
    assert proc.killed and b.options.read_bytes() == original and b not in bench._open_benches
    assert not b.hook_dst.exists()
    assert bench.stop_open_tests() == 0              # a second close finds nothing left to stop
    with pytest.raises(bench.BenchError, match="stopped"):
        b._launch(None, {"tag": "x"}, True, 100)     # the background thread cannot start DCS any more


def test_restore_runs_at_exit_and_from_the_window_close_hook(tmp_path):
    # A program that ends while its test thread is mid-test: atexit puts options.lua back.
    import shutil
    import sys
    from test_core import FIX
    cfg = tmp_path / "Config"
    cfg.mkdir()
    shutil.copy(FIX / "options.DCS.lua", cfg / "options.lua")
    original = (cfg / "options.lua").read_bytes()
    script = (
        "import sys, threading, time\n"
        "from pathlib import Path\n"
        "from dcstune import bench\n"
        "bench.dcs_running = lambda: False\n"
        "bench.gpu_idle_check = lambda: (0.0, 0.0)\n"
        "root = Path(sys.argv[1])\n"
        "b = bench.Bench({'path': str(root), 'name': 'DCS', 'options': str(root / 'Config' / 'options.lua')},"
        " root / 'DCS.exe', log=lambda m: None)\n"
        "def test():\n"
        "    with b:\n"
        "        b.session.write_trial({'graphics.maxFPS': 300})\n"
        "        time.sleep(60)\n"
        "threading.Thread(target=test, daemon=True).start()\n"
        "while not (root / 'Config' / 'dcstune-journal.json').exists(): time.sleep(0.05)\n"
        "time.sleep(0.3)\n"
        "assert b'maxFPS\"] = 300' in (root / 'Config' / 'options.lua').read_bytes()\n")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    done = subprocess.run([sys.executable, "-c", script, str(tmp_path)], cwd=root, capture_output=True,
                          text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert (cfg / "options.lua").read_bytes() == original and not (cfg / "dcstune-journal.json").exists()
    # The window's close event and the end of the window loop both call the same restore.
    import inspect
    from dcstune import ui
    main_src = inspect.getsource(ui.main)
    assert "window.events.closed += stop_open_tests" in main_src
    assert main_src.index("webview.start()") < main_src.rindex("stop_open_tests()")


def test_a_dcs_crash_puts_the_settings_back_at_once(tmp_path, monkeypatch):
    bench, b = _bench(tmp_path, monkeypatch)
    original = b.options.read_bytes()
    (tmp_path / "Logs").mkdir()
    log = tmp_path / "Logs" / "dcs.log"
    clock = [1000.0]
    monkeypatch.setattr(bench.time, "time", lambda: clock[0])
    monkeypatch.setattr(bench.time, "sleep", lambda s: None)
    seen = {}

    class Proc:                                      # DCS crashes and sits behind its crash box
        killed = False
        def __init__(self, args, cwd):
            log.write_text(SYNTHETIC_LOG + "2026-11-21 10:00:20.000 INFO    EDCORE (Main): Minidump created.\n")
            os.utime(log, (clock[0] + 1, clock[0] + 1))
        def wait(self, timeout=None):
            seen.setdefault("trial", _trial_values_in(b))
            clock[0] += 5
            if self.killed:
                return 1
            raise subprocess.TimeoutExpired("DCS.exe", timeout)
        def poll(self): return 1 if self.killed else None
        def kill(self): self.killed = True
    monkeypatch.setattr(bench.subprocess, "Popen", Proc)
    b.fps_cap = 300
    with b:
        with pytest.raises(bench.DcsCrashed, match="DCS crashed during startup") as e:
            b._launch(None, {"tag": "x"}, True, 600)
        assert seen["trial"]                         # the trial values were in place while DCS ran
        assert b.options.read_bytes() == original    # and are gone before the test winds down
        assert not b.session.journal.exists()
        assert (tmp_path / "Config" / "dcstune-last-failure.log").exists()
    assert e.value.fatal and clock[0] - 1000 < 60    # not the ten-minute timeout
    assert b.options.read_bytes() == original


def test_a_crash_that_closes_dcs_is_not_retried(tmp_path, monkeypatch):
    bench, b = _bench(tmp_path, monkeypatch)
    original = b.options.read_bytes()
    (tmp_path / "Logs").mkdir()
    log = tmp_path / "Logs" / "dcs.log"
    monkeypatch.setattr(bench.time, "sleep", lambda s: None)
    starts = []

    class Proc:                                      # DCS writes its crash report and closes
        def __init__(self, args, cwd):
            starts.append(args)
            log.write_text(SYNTHETIC_LOG + "DCSTUNE (Main): hook loaded\nMinidump created.\n")
            os.utime(log, (bench.time.time() + 1, bench.time.time() + 1))
        def wait(self, timeout=None): return 1
        def poll(self): return 1
    monkeypatch.setattr(bench.subprocess, "Popen", Proc)
    with b:
        with pytest.raises(bench.DcsCrashed, match="during the test"):
            b._launch(None, {"tag": "x"}, True, 100)
        assert b.options.read_bytes() == original
    assert len(starts) == 1
