"""Hardware and DCS discovery (Windows). Read-only."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # windowed app: never flash a console

_PS = r"""
$ErrorActionPreference='SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$gpus = @()
$reg = 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
$vram = @{}
Get-ChildItem $reg | ForEach-Object {
  $p = Get-ItemProperty $_.PSPath
  if ($p.DriverDesc -and $p.'HardwareInformation.qwMemorySize') { $vram[$p.DriverDesc] = [int64]$p.'HardwareInformation.qwMemorySize' }
}
Get-CimInstance Win32_VideoController | ForEach-Object {
  $m = $vram[$_.Name]; if (-not $m) { $m = [int64]$_.AdapterRAM }
  $gpus += @{ name=$_.Name; driver=$_.DriverVersion; vram_mb=[int]($m/1MB);
              width=$_.CurrentHorizontalResolution; height=$_.CurrentVerticalResolution; refresh=$_.CurrentRefreshRate }
}
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
# DCS install: every place it is known to be recorded, then the usual folders on every drive.
# Standalone writes the Eagle Dynamics key; Steam writes only its own library list.
$cands = New-Object System.Collections.Generic.List[object]
function Add-Cand($path, $name, $source) { if ($path) { $cands.Add(@{ path=[string]$path; name=[string]$name; source=$source }) } }
foreach ($k in 'HKCU:\Software\Eagle Dynamics\*','HKLM:\SOFTWARE\Eagle Dynamics\*','HKLM:\SOFTWARE\WOW6432Node\Eagle Dynamics\*') {
  Get-ItemProperty $k | ForEach-Object { Add-Cand $_.Path $_.PSChildName 'registry' }
}
foreach ($k in 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*','HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*') {
  Get-ItemProperty $k | Where-Object { $_.DisplayName -like 'DCS World*' -or $_.DisplayName -like 'Digital Combat Simulator*' -or $_.PSChildName -eq 'Steam App 223750' } |
    ForEach-Object { Add-Cand $_.InstallLocation $_.DisplayName 'installed programs' }
}
$libs = @()
$steam = (Get-ItemProperty 'HKCU:\Software\Valve\Steam').SteamPath
if (-not $steam) { $steam = (Get-ItemProperty 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam').InstallPath }
if ($steam) {
  $libs += $steam
  $vdf = Join-Path $steam 'steamapps\libraryfolders.vdf'
  if (Test-Path $vdf) { Select-String -Path $vdf -Pattern '"path"\s+"([^"]+)"' | ForEach-Object { $libs += $_.Matches[0].Groups[1].Value.Replace('\\','\') } }
}
# Local disks only: network drives can stall.
# DriveType 2 too: some external USB disks report as removable. Size is empty for a card reader
# or DVD drive with nothing in it, so those are skipped and never asked for.
$drives = @(Get-CimInstance Win32_LogicalDisk | Where-Object { ($_.DriveType -eq 3 -or $_.DriveType -eq 2) -and $_.Size } |
            ForEach-Object { $_.DeviceID + '\' })
foreach ($d in $drives) { $libs += (Join-Path $d 'SteamLibrary'); $libs += (Join-Path $d 'Steam'); $libs += (Join-Path $d 'Program Files (x86)\Steam'); $libs += (Join-Path $d 'Games\SteamLibrary') }
foreach ($l in $libs) { Add-Cand (Join-Path $l 'steamapps\common\DCSWorld') 'DCS World (Steam)' 'Steam' }
foreach ($d in $drives) {
  foreach ($pat in 'Program Files\Eagle Dynamics\DCS*','Program Files (x86)\Eagle Dynamics\DCS*','Eagle Dynamics\DCS*','DCS World*','DCS','Games\DCS World*','Games\Eagle Dynamics\DCS*') {
    Get-Item (Join-Path $d $pat) | Where-Object { $_.PSIsContainer } | ForEach-Object { Add-Cand $_.FullName $_.Name 'folder search' }
  }
}
$installs = @(); $seen = @{}
foreach ($c in $cands) {
  $p = $c.path.TrimEnd('\')
  if (-not (Test-Path (Join-Path $p 'bin\DCS.exe')) -and -not (Test-Path (Join-Path $p 'bin-mt\DCS.exe'))) { continue }
  $key = (Resolve-Path $p).Path.ToLower()
  if ($seen[$key]) { continue }; $seen[$key] = 1
  $variant = ''
  $vf = Join-Path $p 'dcs_variant.txt'
  if (Test-Path $vf) { $variant = (Get-Content $vf -Raw).Trim() }
  $ver = ''
  $au = Join-Path $p 'autoupdate.cfg'
  if (Test-Path $au) { try { $ver = (Get-Content $au -Raw | ConvertFrom-Json).version } catch {} }
  $media = ''
  try { $media = (Get-Partition -DriveLetter $p.Substring(0,1) | Get-Disk | Get-PhysicalDisk | Select-Object -First 1).MediaType } catch {}
  $installs += @{ name=$c.name; path=$p; variant=$variant; version=$ver; media="$media"; source=$c.source;
                  mt=(Test-Path (Join-Path $p 'bin-mt\DCS.exe')) }
}
# Saved Games: where Windows really keeps it (it can be moved to another drive), plus the defaults.
$sgs = @()
foreach ($k in 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders','HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders') {
  $v = (Get-ItemProperty $k).'{4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4}'
  if ($v) { $sgs += [Environment]::ExpandEnvironmentVariables($v) }
}
$sgs += (Join-Path $env:USERPROFILE 'Saved Games')
foreach ($d in $drives) { $sgs += (Join-Path $d "Users\$env:USERNAME\Saved Games"); $sgs += (Join-Path $d 'Saved Games') }
if ($env:OneDrive) { $sgs += (Join-Path $env:OneDrive 'Saved Games') }
$profiles = @(); $pseen = @{}
foreach ($sg in $sgs) {
  if (-not (Test-Path $sg)) { continue }
  Get-ChildItem $sg -Directory -Filter 'DCS*' | ForEach-Object {
    $o = Join-Path $_.FullName 'Config\options.lua'
    $key = $_.FullName.ToLower()
    if ((Test-Path $o) -and -not $pseen[$key]) {
      $pseen[$key] = 1
      $profiles += @{ name=$_.Name; path=$_.FullName; options=$o; modified=(Get-Item $o).LastWriteTime.ToString('s') }
    }
  }
}
$xr = 'SOFTWARE\Khronos\OpenXR\1'
$layers = @()
foreach ($hive in 'HKLM:','HKCU:') {
  $k = Get-Item "$hive\$xr\ApiLayers\Implicit"
  if ($k) { foreach ($n in $k.Property) { if ($k.GetValue($n) -eq 0) { $layers += [string]$n } } }
}
$pimax = ''
$pp = Join-Path $env:LOCALAPPDATA 'Pimax\runtime\profile.json'
if (Test-Path $pp) { $pimax = [string](Get-Content $pp -Raw) }
$vr = @{ runtime=[string](Get-ItemProperty "HKLM:\$xr").ActiveRuntime; layers=$layers; pimax_profile=$pimax }
@{ cpu=$cpu.Name.Trim(); cores=$cpu.NumberOfCores; vr=$vr;
   ram_gb=[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB);
   gpus=$gpus; installs=$installs; profiles=$profiles;
   dcs_running=[bool](Get-Process DCS,DCS_server -ErrorAction SilentlyContinue) } | ConvertTo-Json -Depth 5 -Compress
"""


def _as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def primary_display() -> dict | None:
    """Current mode of the Windows primary display: the one DCS opens on. The graphics
    card's own figures (above) describe just one of its displays, and on a PC with two
    monitors that can be the wrong one."""
    try:
        import ctypes
        from ctypes import wintypes as w

        class DEVMODE(ctypes.Structure):
            _fields_ = [("name", w.WCHAR * 32), ("spec", w.WORD), ("driver", w.WORD), ("size", w.WORD),
                        ("extra", w.WORD), ("fields", w.DWORD), ("union", ctypes.c_byte * 16),
                        ("color", ctypes.c_short), ("duplex", ctypes.c_short), ("yres", ctypes.c_short),
                        ("tt", ctypes.c_short), ("collate", ctypes.c_short), ("form", w.WCHAR * 32),
                        ("logpixels", w.WORD), ("bpp", w.DWORD), ("width", w.DWORD), ("height", w.DWORD),
                        ("flags", w.DWORD), ("hz", w.DWORD), ("icm", w.DWORD * 8)]

        user32 = ctypes.windll.user32
        dm = DEVMODE()
        dm.size = ctypes.sizeof(DEVMODE)
        if not user32.EnumDisplaySettingsW(None, -1, ctypes.byref(dm)) or not dm.width or not dm.height:
            return None
        return {"width": int(dm.width), "height": int(dm.height), "refresh": int(dm.hz) if dm.hz > 1 else None,
                "count": int(user32.GetSystemMetrics(80)) or 1}        # 80 = number of monitors
    except Exception:
        return None


def collect() -> dict:
    # A script file, not stdin: "powershell -Command -" silently drops multi-line blocks.
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "dcstune-sysinfo.ps1"
        script.write_text(_PS, encoding="utf-8")
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            capture_output=True, timeout=90, creationflags=NO_WINDOW)
    # UTF-8 both ways: folder names with accents (C:\Users\José) must survive, and a byte the
    # default code page cannot decode must never break the start (beta issue #8).
    out = proc.stdout.decode("utf-8", errors="replace").lstrip("\ufeff")
    if "{" not in out:
        raise RuntimeError("could not read hardware information: "
                           + (proc.stderr.decode("utf-8", errors="replace").strip()[:300] or "no output"))
    raw = json.loads(out[out.index("{"):])
    raw["display"] = primary_display()
    return apply_choices(normalize(raw))


# Display drivers that are not a graphics card DCS could render on.
VIRTUAL_GPU = r"Microsoft Basic|Remote Display|Virtual Display|Parsec|Meta Virtual|IddCx|Citrix|VMware|Hyper-V"


def normalize(raw: dict) -> dict:
    info = dict(raw)
    for k in ("gpus", "installs", "profiles"):
        info[k] = _as_list(raw.get(k))
    if isinstance(info.get("vr"), dict):
        info["vr"] = dict(info["vr"], layers=_as_list(info["vr"].get("layers")))
    # The GPU DCS renders on = the strongest one, whether or not it drives a display: on most
    # gaming laptops the built-in chip drives the screen and the RTX card renders behind it
    # (beta issue #6: an RTX 4090 laptop was rated as its integrated graphics).
    from .model import tier_score
    real = [g for g in info["gpus"] if not re.search(VIRTUAL_GPU, g.get("name") or "", re.I)] or info["gpus"]
    best = max(real, key=lambda g: (tier_score("gpu", g.get("name"), 0)[0], g.get("vram_mb") or 0)) if real else None
    if best and not best.get("width"):
        shown = next((g for g in info["gpus"] if g.get("width")), None)
        if shown:
            best = dict(best, width=shown["width"], height=shown["height"], refresh=shown.get("refresh"))
    info["gpu"] = best
    # The display DCS runs on is the Windows primary one; it replaces the card's own figures.
    d = info.get("display")
    if info["gpu"] and isinstance(d, dict) and d.get("width") and d.get("height"):
        info["gpu"] = dict(info["gpu"], width=d["width"], height=d["height"],
                           refresh=d.get("refresh") or info["gpu"].get("refresh"))
    return info


def gpu_vendor(info: dict) -> str:
    forced = os.environ.get("DCSTUNE_FORCE_VENDOR")     # testing: run the AMD/Intel path on any card
    if forced in ("nvidia", "other"):
        return forced
    name = ((info.get("gpu") or {}).get("name") or "").lower()
    if "nvidia" in name or "geforce" in name or "rtx" in name:
        return "nvidia"
    return "other"


class SetupNeeded(RuntimeError):
    """DCS or its Saved Games folder could not be found; the player can point to it."""

    def __init__(self, what: str, message: str):
        super().__init__(message)
        self.what = what            # "install" or "profile"


def choices_file() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "DCS Graphics Optimizer" / "folders.json"


def load_choices() -> dict:
    try:
        d = json.loads(choices_file().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def install_record(path: str, source: str = "chosen") -> dict | None:
    """An install entry for a folder, or None when it does not contain DCS.exe."""
    root = Path(path)
    if root.name.lower() in ("bin", "bin-mt") and (root / "DCS.exe").is_file():
        root = root.parent                       # the player picked the bin folder itself
    if not any((root / sub / "DCS.exe").is_file() for sub in ("bin", "bin-mt")):
        return None

    def read(name):
        try:
            return (root / name).read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return ""
    try:
        version = json.loads(read("autoupdate.cfg") or "{}").get("version", "")
    except ValueError:
        version = ""
    return {"name": root.name, "path": str(root), "variant": read("dcs_variant.txt"), "version": version,
            "media": "", "source": source, "mt": (root / "bin-mt" / "DCS.exe").is_file()}


def profile_record(path: str) -> dict | None:
    """A profile entry for a Saved Games\\DCS folder, or None when it has no Config\\options.lua.
    Picking Saved Games itself, or the Config folder, is accepted too."""
    p = Path(path)
    if p.name.lower() == "config":
        p = p.parent
    if not (p / "Config" / "options.lua").is_file():
        subs = [s for s in p.glob("DCS*") if (s / "Config" / "options.lua").is_file()] if p.is_dir() else []
        if not subs:
            return None
        p = max(subs, key=lambda s: (s / "Config" / "options.lua").stat().st_mtime)
    o = p / "Config" / "options.lua"
    import datetime
    return {"name": p.name, "path": str(p), "options": str(o), "chosen": True,
            "modified": datetime.datetime.fromtimestamp(o.stat().st_mtime).strftime("%Y-%m-%dT%H:%M:%S")}


def choose(what: str, path: str) -> str:
    """Remember a folder the player picked. Returns a sentence for the window."""
    path = (path or "").strip().strip('"')
    if what == "install":
        rec = install_record(path)
        if not rec:
            raise RuntimeError(f"DCS.exe was not found in {path}. Pick the main DCS World folder, "
                               "the one that contains the bin folder.")
        saved, msg = rec["path"], f"Using DCS World in {rec['path']}."
    elif what == "profile":
        rec = profile_record(path)
        if not rec:
            raise RuntimeError(f"No DCS settings were found in {path}. Pick your Saved Games\\DCS folder, "
                               "the one that contains Config\\options.lua.")
        saved, msg = rec["path"], f"Using the DCS settings in {rec['path']}."
    else:
        raise ValueError(what)
    d = load_choices()
    d[what] = saved
    f = choices_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return msg


def apply_choices(info: dict, choices: dict | None = None) -> dict:
    """Put folders the player picked in front of the ones found automatically."""
    choices = load_choices() if choices is None else choices
    info = dict(info)
    inst = install_record(choices["install"]) if choices.get("install") else None
    if inst:
        info["installs"] = [inst] + [i for i in info.get("installs", [])
                                     if Path(i["path"]).resolve() != Path(inst["path"]).resolve()]
    prof = profile_record(choices["profile"]) if choices.get("profile") else None
    if prof:
        info["profiles"] = [prof] + [p for p in info.get("profiles", [])
                                     if Path(p["path"]).resolve() != Path(prof["path"]).resolve()]
    return info


def pick_profile(info: dict, name: str | None = None) -> dict:
    profiles = info["profiles"]
    if not profiles:
        raise SetupNeeded("profile", "Your DCS settings folder was not found (Saved Games\\DCS with "
                                     "Config\\options.lua). If you have started DCS on this PC before, "
                                     "use Browse to show where your Saved Games\\DCS folder is.")
    if name:
        for p in profiles:
            if p["name"].lower() == name.lower():
                return p
        raise RuntimeError(f"profile {name!r} not found; have {[p['name'] for p in profiles]}")
    for p in profiles:
        if p.get("chosen"):
            return p
    # Default: the profile DCS itself would use (install variant), else most recently used.
    for inst in info["installs"]:
        want = "DCS" + ("." + inst["variant"] if inst.get("variant") else "")
        for p in profiles:
            if p["name"].lower() == want.lower():
                return p
    return max(profiles, key=lambda p: p["modified"])


def pick_install(info: dict) -> dict:
    if not info["installs"]:
        raise SetupNeeded("install", "DCS World was not found on this PC (searched the registry, Steam "
                                     "libraries and the usual folders on every drive). Use Browse to show "
                                     "where DCS World is installed.")
    return info["installs"][0]


def dcs_exe(install: dict) -> Path:
    root = Path(install["path"])
    for sub in ("bin-mt", "bin"):
        exe = root / sub / "DCS.exe"
        if exe.exists():
            return exe
    raise RuntimeError(f"DCS.exe not found under {root}")
