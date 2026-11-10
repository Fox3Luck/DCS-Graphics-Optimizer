"""DCS Graphics Optimizer command line.

  python -m dcstune rate                 scorecard, no DCS launch
  python -m dcstune bench                benchmark current settings once
  python -m dcstune optimize [--full]    measure, search, recommend (writes a report)
  python -m dcstune apply                apply the last recommendation (after backup)
  python -m dcstune undo                 restore the settings from before the last apply
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import model as M
from . import optimize, rate, sysinfo
from .optionslua import Options, backup, list_backups, recover, atomic_write


def _context(args):
    info = sysinfo.collect()
    profile = sysinfo.pick_profile(info, args.profile)
    if recover(profile["options"]):
        print("Restored your original settings from an interrupted earlier run.")
    opts = Options.load(profile["options"])
    return info, profile, opts, rate.flat_options(opts)


def _report_path(profile) -> Path:
    return Path(profile["path"]) / "Config" / "dcstune-report.json"


def _print_card(title, card, lines):
    print(f"\n{title}: {card['grade']}  ({card['score']}/100)")
    for line in lines:
        print("  - " + line)


def cmd_rate(args):
    info, profile, _, flat = _context(args)
    machine = rate.rate_machine(info)
    fit = rate.rate_settings(info, flat, machine, calibration=rate.load_calibration(profile, info, flat))
    if args.json:
        print(json.dumps({"profile": profile["name"], "machine": machine, "settings": fit}, indent=1))
        return 0
    print(f"Profile: {profile['name']}")
    _print_card("Your PC for DCS", machine, machine["reasons"])
    _print_card(f"Your settings ({fit['basis']})", fit,
                [f"[{f['severity']}] {f['text']}" for f in fit["findings"]])
    return 0


def _bench(info, profile, args):
    from .bench import Bench
    return Bench(profile, sysinfo.dcs_exe(sysinfo.pick_install(info)), scene_sec=args.scene_sec)


def cmd_bench(args):
    info, profile, _, _ = _context(args)
    with _bench(info, profile, args) as b:
        b.keep_raw_dir = args.keep_raw
        for _ in range(args.repeat):
            r = b.measure(json.loads(args.set) if args.set else None)
            for s in r["raw"]["scenes"]:
                print(f"    {s['name']:9} avg {s['avg_fps']:7.1f}  1% low {s['p1_low_fps']:7.1f}  "
                      f"median {s['median_ms']:.2f} ms  max {s['max_ms']:.1f} ms  stutters {s['stutters']}")
    return 0


def cmd_optimize(args):
    # Same code path as the window, so both write the same report.
    from .ui import Engine
    engine = Engine(args.profile)
    if engine.scorecard()["vr"]:
        print("VR is switched on in this profile. VR tuning comes in the next version; "
              "the benchmark runs flat-screen and your VR settings are left alone.")
    report = engine.optimize(args.full, print)
    machine = engine.scorecard()["machine"]
    _print_card("Your PC for DCS", machine, machine["reasons"])
    _print_card("Current settings (measured)", report["before"], [f["text"] for f in report["before"]["findings"]])
    if "changes" not in report:
        print("\nYour current settings are already the best match we found. Nothing to change.")
        return 0
    _print_card("Recommended settings (measured)", report["after"], [
        f"{c['label']}: {c['from']} -> {c['to']}" for c in report["change_list"]])
    if not report["target_reached"]:
        print(f"\nNote: this PC cannot hold {report['target_fps']} FPS in the heaviest scene even at the "
              "lowest settings; the recommendation is the smoothest result we measured.")
    print("\nNothing has been changed. Run 'python -m dcstune apply' to use these settings.")
    return 0


def cmd_apply(args):
    from .ui import Engine
    print(Engine(args.profile).apply() + " 'python -m dcstune undo' puts them back.")
    return 0


def cmd_undo(args):
    from .ui import Engine
    print(Engine(args.profile).undo())
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="dcstune", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profile", help="Saved Games profile folder name (default: the one DCS uses)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("rate"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_rate)
    for name, fn in (("bench", cmd_bench), ("optimize", cmd_optimize)):
        s = sub.add_parser(name)
        if name == "bench":
            s.add_argument("--scene-sec", type=int, default=25)
        if name == "bench":
            s.add_argument("--repeat", type=int, default=1)
            s.add_argument("--keep-raw", help="folder to keep raw frame times in")
            s.add_argument("--set", help='JSON of trial settings, e.g. {"graphics.shadows": 0}')
        if name == "optimize":
            s.add_argument("--full", action="store_true", help="measure every setting (about an hour)")
        s.set_defaults(fn=fn)
    sub.add_parser("apply").set_defaults(fn=cmd_apply)
    sub.add_parser("undo").set_defaults(fn=cmd_undo)
    args = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)   # progress shows live even when redirected
    try:
        return args.fn(args)
    except Exception as e:  # player-facing: one clear line, not a traceback
        print(f"DCS Graphics Optimizer stopped: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
