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
import time
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
        subprocess.Popen(["explorer.exe", sys.executable])
    except OSError:
        return False
    return True
