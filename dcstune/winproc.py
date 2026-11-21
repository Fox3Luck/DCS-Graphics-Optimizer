# DCS Graphics Optimizer - Fox3 Managed Solutions Inc.
# Created 2026-11-14. Handles a web-browser setting that would stop DCS from starting, and starts
# other programs (DCS above all) without the packaged app's own DLL folder (issue #58).
"""The "prefer System32 DLLs" policy a web browser can pass on (beta issue #1).

Firefox-based browsers switch on the PreferSystem32 image-load mitigation for themselves, and
every program they start inherits it: browser -> optimizer -> DCS. DCS ships DLLs whose names
collide with Windows' own (bin-mt\\Input.dll vs System32\\Input.dll), so with the policy on DCS
loads the wrong one and stops with "procedure entry point ... could not be located". (Diagnosed
by the reporter of issue #1.)

Windows does not let a process switch the policy off for a child (tested 2026-11-14: the
PROC_THREAD_ATTRIBUTE_MITIGATION_POLICY "always off" request is ignored), but a program started
by Explorer does not have it. So when the optimizer finds the policy on, it asks Explorer to
start it again and closes itself; if that does not help, the test refuses to start DCS and
says what to do.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path

PROCESS_IMAGE_LOAD_POLICY = 10          # PROCESS_MITIGATION_POLICY enum: ProcessImageLoadPolicy
PREFER_SYSTEM32_BIT = 0x4               # PROCESS_MITIGATION_IMAGE_LOAD_POLICY.PreferSystem32Images
RESTART_MARK = Path(tempfile.gettempdir()) / "dcsgo-restarted-by-explorer"
RESTART_WINDOW_SEC = 120

ADVICE = ("Windows started this program with a setting from your web browser that makes DCS load the "
          "wrong files, so DCS would stop with an \"entry point not found\" error. Close the optimizer "
          "and start DCSGraphicsOptimizer.exe by double-clicking it in File Explorer, not from the "
          "browser's download list.")


def prefer_system32_on() -> bool | None:
    """Whether this process has the policy on; None if it cannot be read (not Windows)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes as w
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = w.HANDLE
    k32.GetProcessMitigationPolicy.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, ctypes.c_size_t]
    flags = w.DWORD(0)
    if not k32.GetProcessMitigationPolicy(k32.GetCurrentProcess(), PROCESS_IMAGE_LOAD_POLICY,
                                          ctypes.byref(flags), ctypes.sizeof(flags)):
        return None
    return bool(flags.value & PREFER_SYSTEM32_BIT)


def restart_through_explorer() -> bool:
    """Called once at start-up of the packaged app. True means a clean copy was started and
    this one should exit. Never restarts twice in a row (no loop if Explorer has it too)."""
    if not getattr(sys, "frozen", False) or not prefer_system32_on():
        return False
    try:
        if time.time() - RESTART_MARK.stat().st_mtime < RESTART_WINDOW_SEC:
            return False                       # we were just restarted and it did not help
    except OSError:
        pass
    try:
        RESTART_MARK.write_text(str(os.getpid()))
        popen(["explorer.exe", sys.executable])
    except OSError:
        return False
    return True


# -- starting other programs from the packaged app (issue #58) ----------------------------------------
# The packaged app is a PyInstaller single file. Its bootloader unpacks into a temporary _MEIxxxx folder,
# points this process's DLL search at that folder (SetDllDirectoryW) and sets a few _PYI*/_MEIPASS*
# variables. A program started from here inherits all of it: a tester's DCS loaded VCRUNTIME140.dll and
# VCRUNTIME140_1.dll from our _MEI folder instead of System32 and crashed while building its menus, every
# time the optimizer started it. Every program the optimizer starts goes through popen()/run() below, which
# start it with Windows' normal DLL search and without the bootloader's variables. Outside the packaged
# app (no sys._MEIPASS) and off Windows they are plain subprocess.Popen/subprocess.run.

IS_WINDOWS = sys.platform == "win32"
_DLL_LOCK = threading.Lock()       # SetDllDirectoryW is process-wide: one launch at a time switches it


def _bundle_dir() -> str | None:
    """The _MEIxxxx folder of the packaged app; None when running from source."""
    return getattr(sys, "_MEIPASS", None)


def _kernel32():
    import ctypes
    return ctypes.windll.kernel32


def _bootloader_var(name: str) -> bool:
    n = name.upper()
    return n.startswith("_MEIPASS") or n.startswith("_PYI")       # _MEIPASS2, _PYI_APPLICATION_HOME_DIR, ...


def _inside(entry: str, folder: str) -> bool:
    norm = lambda p: os.path.normcase(os.path.normpath(p.strip().strip('"')))
    e, f = norm(entry), norm(folder)
    return e == f or e.startswith(f.rstrip("\\/") + os.sep)


def clean_env(base=None) -> dict:
    """A copy of the environment (or of `base`) for a program started from the packaged app: the
    bootloader's _MEIPASS*/_PYI* variables removed and the _MEI folder taken out of PATH."""
    base = os.environ if base is None else base
    env = {k: v for k, v in base.items() if not _bootloader_var(k)}
    bundle = _bundle_dir()
    if bundle:
        for key in [k for k in env if k.upper() == "PATH"]:
            env[key] = os.pathsep.join(p for p in env[key].split(os.pathsep) if p and not _inside(p, bundle))
    return env


@contextmanager
def clean_dll_search():
    """While inside: this process's DLL search is Windows' default, so a program started now does not
    inherit the _MEI folder. The packaged app's own setting is put back afterwards."""
    bundle = _bundle_dir()
    if not (IS_WINDOWS and bundle):
        yield
        return
    with _DLL_LOCK:
        k32 = _kernel32()
        k32.SetDllDirectoryW(None)
        try:
            yield
        finally:
            k32.SetDllDirectoryW(bundle)


def popen(args, **kw) -> subprocess.Popen:
    """subprocess.Popen for any program the optimizer starts (DCS above all)."""
    if not _bundle_dir():
        return subprocess.Popen(args, **kw)
    kw["env"] = clean_env(kw.get("env"))
    with clean_dll_search():
        return subprocess.Popen(args, **kw)


def run(args, *, input=None, timeout=None, check=False, capture_output=False, **kw) -> subprocess.CompletedProcess:
    """subprocess.run for any program the optimizer starts. In the packaged app the program is started
    through popen() so the DLL switch lasts only while Windows creates it, not while it runs."""
    if not _bundle_dir():
        return subprocess.run(args, input=input, timeout=timeout, check=check, capture_output=capture_output, **kw)
    if capture_output:
        kw["stdout"] = kw["stderr"] = subprocess.PIPE
    if input is not None:
        kw["stdin"] = subprocess.PIPE
    with popen(args, **kw) as proc:
        try:
            out, err = proc.communicate(input, timeout=timeout)
        except BaseException:              # as subprocess.run: never leave the program running
            proc.kill()
            proc.wait()
            raise
        code = proc.poll()
    if check and code:
        raise subprocess.CalledProcessError(code, args, out, err)
    return subprocess.CompletedProcess(args, code, out, err)


def bundled_runtime_lines(dcs_log: str) -> list[str]:
    """Lines of a DCS log (its module list) that show a Visual C++ runtime DLL loaded from a _MEI folder:
    DCS was started with the packaged app's DLL search (issue #58)."""
    return [ln.strip() for ln in dcs_log.splitlines()
            if "vcruntime" in ln.lower() and ".dll" in ln.lower() and "_mei" in ln.lower()]


BUNDLED_RUNTIME_WARNING = (
    "WARNING: DCS loaded the Microsoft Visual C++ runtime (VCRUNTIME*.dll) from this program's own "
    "temporary folder (_MEI...) instead of from Windows. That is the problem behind GitHub issue #58 and can "
    "make DCS crash while it starts. Please tell us in issue #58.")
