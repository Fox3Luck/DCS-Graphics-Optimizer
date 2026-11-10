# Builds dist\DCSTune.exe (single file, no install needed). Run on Windows from the repo root:
#   powershell -ExecutionPolicy Bypass -File build\build.ps1
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path .buildenv)) { python -m venv .buildenv }
& .buildenv\Scripts\python -m pip install --quiet --upgrade pip
& .buildenv\Scripts\python -m pip install --quiet pyinstaller pywebview
& .buildenv\Scripts\pyinstaller --noconfirm --clean --onefile --windowed --name DCSTune `
    --add-data "$PWD\dcstune\data;dcstune\data" --add-data "$PWD\dcstune\ui.html;dcstune" `
    --add-data "$PWD\hook;hook" --add-data "$PWD\mission\dcstune_bench.miz;mission" `
    --distpath dist --workpath build\work --specpath build\work app.py
Get-Item dist\DCSTune.exe | ForEach-Object { "{0}  {1:N1} MB" -f $_.FullName, ($_.Length/1MB) }
(Get-FileHash dist\DCSTune.exe -Algorithm SHA256).Hash
