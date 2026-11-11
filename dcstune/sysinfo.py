"""Hardware and DCS discovery (Windows). Read-only."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # windowed app: never flash a console

_PS = r"""
$ErrorActionPreference='SilentlyContinue'
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
$installs = @()
Get-ItemProperty 'HKCU:\Software\Eagle Dynamics\*' | ForEach-Object {
  if ($_.Path -and (Test-Path $_.Path)) {
    $variant = ''
    $vf = Join-Path $_.Path 'dcs_variant.txt'
    if (Test-Path $vf) { $variant = (Get-Content $vf -Raw).Trim() }
    $ver = ''
    $au = Join-Path $_.Path 'autoupdate.cfg'
    if (Test-Path $au) { try { $ver = (Get-Content $au -Raw | ConvertFrom-Json).version } catch {} }
    $letter = $_.Path.Substring(0,1)
    $media = ''
    try { $media = (Get-Partition -DriveLetter $letter | Get-Disk | Get-PhysicalDisk | Select-Object -First 1).MediaType } catch {}
    $installs += @{ name=$_.PSChildName; path=$_.Path; variant=$variant; version=$ver; media="$media";
                    mt=(Test-Path (Join-Path $_.Path 'bin-mt\DCS.exe')) }
  }
}
$sg = Join-Path $env:USERPROFILE 'Saved Games'
$known = (New-Object -ComObject Shell.Application).Namespace('shell:::{4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4}').Self.Path
if ($known) { $sg = $known }
$profiles = @()
Get-ChildItem $sg -Directory -Filter 'DCS*' | ForEach-Object {
  $o = Join-Path $_.FullName 'Config\options.lua'
  if (Test-Path $o) { $profiles += @{ name=$_.Name; path=$_.FullName; options=$o; modified=(Get-Item $o).LastWriteTime.ToString('s') } }
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


def collect() -> dict:
    # A script file, not stdin: "powershell -Command -" silently drops multi-line blocks.
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "dcstune-sysinfo.ps1"
        script.write_text(_PS, encoding="utf-8")
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            capture_output=True, text=True, timeout=90, creationflags=NO_WINDOW)
    out = proc.stdout
    if "{" not in out:
        raise RuntimeError("could not read hardware information: " + (proc.stderr.strip()[:300] or "no output"))
    return normalise(json.loads(out[out.index("{"):]))


def normalise(raw: dict) -> dict:
    info = dict(raw)
    for k in ("gpus", "installs", "profiles"):
        info[k] = _as_list(raw.get(k))
    if isinstance(info.get("vr"), dict):
        info["vr"] = dict(info["vr"], layers=_as_list(info["vr"].get("layers")))
    # Primary GPU = the one driving a display with the most VRAM (skips idle iGPUs).
    active = [g for g in info["gpus"] if g.get("width")] or info["gpus"]
    info["gpu"] = max(active, key=lambda g: g.get("vram_mb") or 0) if active else None
    return info


def gpu_vendor(info: dict) -> str:
    forced = os.environ.get("DCSTUNE_FORCE_VENDOR")     # testing: run the AMD/Intel path on any card
    if forced in ("nvidia", "other"):
        return forced
    name = ((info.get("gpu") or {}).get("name") or "").lower()
    if "nvidia" in name or "geforce" in name or "rtx" in name:
        return "nvidia"
    return "other"


def pick_profile(info: dict, name: str | None = None) -> dict:
    profiles = info["profiles"]
    if not profiles:
        raise RuntimeError("No DCS profile with Config\\options.lua found under Saved Games")
    if name:
        for p in profiles:
            if p["name"].lower() == name.lower():
                return p
        raise RuntimeError(f"profile {name!r} not found; have {[p['name'] for p in profiles]}")
    # Default: the profile DCS itself would use (install variant), else most recently used.
    for inst in info["installs"]:
        want = "DCS" + ("." + inst["variant"] if inst.get("variant") else "")
        for p in profiles:
            if p["name"].lower() == want.lower():
                return p
    return max(profiles, key=lambda p: p["modified"])


def pick_install(info: dict) -> dict:
    if not info["installs"]:
        raise RuntimeError("DCS World install not found in the registry")
    return info["installs"][0]


def dcs_exe(install: dict) -> Path:
    root = Path(install["path"])
    for sub in ("bin-mt", "bin"):
        exe = root / sub / "DCS.exe"
        if exe.exists():
            return exe
    raise RuntimeError(f"DCS.exe not found under {root}")
