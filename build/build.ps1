# Builds dist\DCSGraphicsOptimizer.exe (single file, no install needed). Run on Windows from the repo root:
#   powershell -ExecutionPolicy Bypass -File build\build.ps1
# Every package that ends up in the exe is pinned to an exact version and file hash in
# build\requirements*.txt; pip refuses anything else. The build never signs: signing is a separate,
# deliberate step on the exact file whose hash is printed at the end.
# -VrTest N builds VR test build N for VR volunteers (in-headset testing switched on). N is the
# number in its release tag (vr-test-N); the build uses it to tell players about a newer VR test build:
#   powershell -ExecutionPolicy Bypass -File build\build.ps1 -VrTest 3
param([int]$VrTest = 0)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Check($what) { if ($LASTEXITCODE -ne 0) { throw "$what failed ($LASTEXITCODE)" } }
if (-not (Test-Path .buildenv)) { python -m venv .buildenv; Check "creating the build environment" }
$py = ".buildenv\Scripts\python.exe"
& $py -m pip install --quiet --disable-pip-version-check --require-hashes --no-deps --only-binary :all: -r build\requirements-first.txt
Check "installing pinned setuptools"
& $py -m pip install --quiet --disable-pip-version-check --require-hashes --no-deps --no-build-isolation -r build\requirements.txt
Check "installing pinned packages"
# Nothing may be in the environment that is not pinned (pip itself comes with Python).
$pinned = Get-Content build\requirements.txt, build\requirements-first.txt | Where-Object { $_ -match '^[A-Za-z0-9_.-]+==' } |
    ForEach-Object { ($_ -split ' ')[0].ToLower().Replace('_', '-') }
$extra = & $py -m pip freeze --disable-pip-version-check | ForEach-Object { $_.ToLower().Replace('_', '-') } | Where-Object { $pinned -notcontains $_ }
if ($extra) { throw "the build environment contains packages that are not pinned: $($extra -join ', ')" }
$marker = "dcstune\data\vr_test_build"
Remove-Item $marker -ErrorAction SilentlyContinue
if ($VrTest) { Set-Content $marker "$VrTest" }
try {
& .buildenv\Scripts\pyinstaller --noconfirm --clean --onefile --windowed --name DCSGraphicsOptimizer `
    --add-data "$PWD\dcstune\data;dcstune\data" --add-data "$PWD\dcstune\ui.html;dcstune" `
    --add-data "$PWD\hook;hook" --add-data "$PWD\mission\dcstune_bench.miz;mission" `
    --distpath dist --workpath build\work --specpath build\work app.py
Check "pyinstaller"
} finally { Remove-Item $marker -ErrorAction SilentlyContinue }
if ($VrTest) { "VR TEST BUILD $VrTest (in-headset testing on). Release it under the tag vr-test-$VrTest." }
"NOT SIGNED. To sign this exact file: build\sign.ps1 -Sha256 <the hash below>"
Get-Item dist\DCSGraphicsOptimizer.exe | ForEach-Object { "{0}  {1:N1} MB" -f $_.FullName, ($_.Length/1MB) }
(Get-FileHash dist\DCSGraphicsOptimizer.exe -Algorithm SHA256).Hash
