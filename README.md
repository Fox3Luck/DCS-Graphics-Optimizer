# DCS Graphics Optimizer

Rates a PC and its DCS World graphics settings, benchmarks alternatives by running DCS
itself, recommends the best-looking settings that hold a smooth frame rate, and applies
them only when the player agrees. Flat-screen only in v1 (VR is planned for v2).

    python -m dcstune rate              scorecard, DCS is not started
    python -m dcstune optimize [--full] benchmark + recommendation (starts DCS several times)
    python -m dcstune apply | undo
    python -m dcstune.ui                the window (Rate / Optimize / Apply / Undo)

**For players:** see the [User Guide](docs/USER-GUIDE.md) for what the tests do, how long they take and what is changed.

Layout: `dcstune/optionslua.py` (byte-preserving options.lua edits, backup, crash
recovery), `sysinfo.py` (hardware + DCS discovery), `model.py` + `data/` (setting levels,
quality weights, frame-time model), `rate.py` (scorecard), `optimize.py` (search),
`bench.py` + `hook/dcstune_bench.lua` + `mission/` (benchmark), `ui.py` + `ui.html` (window).

Tests: `.venv/bin/python -m pytest tests` (needs `pytest`, `lupa`; `pydcs` only to
rebuild the mission with `mission/generate.py`).

Build the Windows app (on Windows): `powershell -ExecutionPolicy Bypass -File build\build.ps1`
produces `dist\DCSGraphicsOptimizer.exe`, a single file that needs no Python and no install.

Status 2026-11-10: scorecard, benchmark, automatic optimize, apply and undo all verified in
real DCS 2.9.31 on one PC (RTX 4080 / 9800X3D). Not yet verified: AMD/Intel GPUs, the
Thorough mode in real DCS, a second PC, VR (planned for v2).
