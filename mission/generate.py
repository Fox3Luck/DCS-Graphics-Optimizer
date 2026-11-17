# DCS Graphics Optimizer - Fox3 Managed Solutions Inc.
# Created 2026-11-10. Builds the test mission (free content only, same every run).
# 2026-11-17: can also build the same three scenes on another map with another aircraft (issue #23).
"""Build a test mission with pydcs: AI-flown, no weapons, no enemies, fixed weather and time, so every
run is the same.

    python mission/generate.py                         -> mission/dcstune_bench.miz (Caucasus, Su-25T: free content)
    python mission/generate.py out.miz syria F-14B     -> the same scenes over Beirut with F-14Bs
    python mission/generate.py --pack                  -> mission/scenes.tar.xz and scenes.json: every map with
                                                          every aircraft the window offers (issue #23)

Scenes (unit names are what the hook's camera follows):
  TUNE-CITY-1  low and slow over the city next to the map's airfield - dense buildings, water, trees
  TUNE-RAMP-1  parked on that airfield's crowded ramp - many aircraft models and shadows
  TUNE-HIGH-1  inside a broken cloud layer
"""
import sys
from pathlib import Path

import dcs
from dcs import cloud_presets, helicopters, mapping, planes, task

# One airfield per map, next to the biggest city the map has, and its height above sea level in meters
# (cloud and flight heights are set from it; Kandahar sits at 1,010 m).
# Per map: the airfield for the ramp scene and its height above sea level in meters (cloud and flight
# heights are set from it), then the middle of the map's biggest city (latitude, longitude) and the
# compass heading the city pass flies on, picked to stay over buildings and clear of high ground.
# The pass is flown 350 m above the ground, so it is kept to one side of anything taller: the Burj
# Khalifa and the towers along Sheikh Zayed Road (Dubai), the TV tower (Berlin), the Eiffel Tower (Paris).
MAPS = {
    "caucasus":       ("dcs.terrain.caucasus", "Caucasus", "Batumi", 10, None, None),
    "syria":          ("dcs.terrain.syria", "Syria", "Beirut-Rafic Hariri", 12, (33.893, 35.502), 20),
    "nevada":         ("dcs.terrain.nevada", "Nevada", "McCarran International", 660, (36.115, -115.173), 0),
    "persiangulf":    ("dcs.terrain.persiangulf", "PersianGulf", "Dubai Intl", 5, (25.220, 55.250), 45),
    "marianaislands": ("dcs.terrain.marianaislands", "MarianaIslands", "Antonio B. Won Pat Intl", 90, (13.500, 144.790), 45),
    "normandy":       ("dcs.terrain.normandy", "Normandy", "Orly", 90, (48.866, 2.352), 90),
    "thechannel":     ("dcs.terrain.thechannel", "TheChannel", "Manston", 50, (51.127, 1.313), 50),
    "falklands":      ("dcs.terrain.falklands", "Falklands", "Port Stanley", 20, (-51.695, -57.855), 90),
    "sinai":          ("dcs.terrain.sinai", "Sinai", "Cairo International Airport", 110, (30.045, 31.236), 0),
    "kola":           ("dcs.terrain.kola", "Kola", "Murmansk International", 80, (68.970, 33.080), 0),
    # Kandahar, not Kabul: open country, where Kabul is ringed by 5,000 m peaks
    "afghanistan":    ("dcs.terrain.afghanistan", "Afghanistan", "Kandahar", 1010, (31.620, 65.710), 90),
    "germany":        ("dcs.terrain.germany", "Germany", "Tempelhof", 50, (52.510, 13.400), 90),
}


def aircraft_type(name: str):
    kind = planes.plane_map.get(name) or helicopters.helicopter_map.get(name)
    if kind is None:
        raise SystemExit(f"unknown aircraft type {name!r}")
    return kind


def build(out: Path, map_key: str = "caucasus", aircraft: str = "Su-25T") -> Path:
    import importlib
    module, cls, airfield, elev, city, heading = MAPS[map_key]
    kind = aircraft_type(aircraft)
    heli = aircraft in helicopters.helicopter_map
    m = dcs.Mission(terrain=getattr(importlib.import_module(module), cls)())
    m.name = "DCS Graphics Optimizer benchmark"
    m.start_time = m.start_time.replace(month=6, day=15, hour=10, minute=0, second=0)
    m.weather.clouds_preset = cloud_presets.Clouds.Broken4.value
    cloud_base = min(elev + 3800, 4200)          # 4,200 m is the highest base this cloud preset allows
    m.weather.clouds_base = cloud_base
    m.weather.wind_at_ground.speed = 0
    m.weather.turbulence_at_ground = 0

    side = m.country("USA")           # the mission file accepts any aircraft type under any country
    field = m.terrain.airports[airfield]
    fp = field.position
    low, low_speed = (350, 450) if not heli else (150, 180)       # height above the ground, km/h
    high, high_speed = (cloud_base + 600, 750) if not heli else (cloud_base + 600, 200)

    def flight(name, start, end, alt, speed_kmh, via=None, above_ground=False):
        # singletons: a pydcs 2-ship spawns 10 m apart and collides
        g = m.flight_group_inflight(side, name, kind, position=start, altitude=alt,
                                    speed=speed_kmh, maintask=task.Nothing, group_size=1)
        for i, u in enumerate(g.units):
            u.name = f"{name}-{i + 1}"
            u.pylons.clear()
        if via:
            g.add_waypoint(via, alt, speed_kmh)
        g.add_waypoint(end, alt, speed_kmh)
        # fly back and forth for as long as the benchmark needs
        g.add_waypoint(start, alt, speed_kmh)
        g.add_waypoint(end, alt, speed_kmh)
        if above_ground:
            for p in g.points:
                p.alt_type = "RADIO"
            for u in g.units:               # the aircraft appears this high above the ground too, not above the sea
                u.alt_type = "RADIO"
        return g

    # 1. city: in toward the airfield's city and on past it
    if map_key == "caucasus":
        kp = m.terrain.airports["Kobuleti"].position      # in from the sea, over Batumi, up the flat coast
        flight("TUNE-CITY", mapping.Point(fp.x - 2000, fp.y - 7000, m.terrain),
               mapping.Point(kp.x, kp.y - 1500, m.terrain), low, low_speed,
               via=mapping.Point(fp.x + 3000, fp.y + 1000, m.terrain))
    else:
        # The timed part starts about 25 seconds after the aircraft appears and lasts 30: start far
        # enough out, for this aircraft's speed, that it is over the middle of the city by then.
        center = mapping.Point.from_latlng(mapping.LatLng(*city), m.terrain)
        run_in = low_speed / 3.6 * 40 + 1500
        flight("TUNE-CITY", center.point_from_heading((heading + 180) % 360, run_in),
               center.point_from_heading(heading, 25000), low, low_speed, via=center, above_ground=True)

    # 2. airfield: one aircraft on the ramp, surrounded by parked ones (as many as the ramp has room for)
    def parked(name):
        g = m.flight_group_from_airport(side, name, kind, field, maintask=task.Nothing,
                                        start_type=dcs.mission.StartType.Cold, group_size=1)
        g.uncontrolled = True          # sits on the ramp, engines off, never moves
        g.units[0].pylons.clear()
        return g
    ramp = parked("TUNE-RAMP")
    ramp.units[0].name = "TUNE-RAMP-1"
    ramp.late_activation = False
    for i in range(8):
        try:
            parked(f"TUNE-PARK-{i}")
        except Exception:               # no more room for this aircraft on this ramp
            break

    # 3. clouds: inside the broken layer
    flight("TUNE-HIGH", mapping.Point(fp.x + 20000, fp.y + 30000, m.terrain),
           mapping.Point(fp.x + 90000, fp.y + 60000, m.terrain), high, high_speed)

    # One spectator-capable slot is not needed: the hook hosts and stays unslotted.
    m.save(str(out))
    return out


# What the window offers. Maps: key -> (name shown, DCS's folder name under Mods\\terrains).
MAP_LABELS = {
    "caucasus": ("Caucasus (Batumi)", "Caucasus"), "syria": ("Syria (Beirut)", "Syria"),
    "nevada": ("Nevada (Las Vegas)", "Nevada"), "persiangulf": ("Persian Gulf (Dubai)", "PersianGulf"),
    "marianaislands": ("Mariana Islands (Guam)", "MarianaIslands"), "normandy": ("Normandy 2.0 (Paris)", "Normandy"),
    "thechannel": ("The Channel (Dover)", "TheChannel"), "falklands": ("South Atlantic (Port Stanley)", "Falklands"),
    "sinai": ("Sinai (Cairo)", "Sinai"), "kola": ("Kola (Murmansk)", "Kola"),
    "afghanistan": ("Afghanistan (Kandahar)", "Afghanistan"), "germany": ("Germany Cold War (Berlin)", "GermanyColdWar"),
}
# Aircraft: DCS type -> (name shown, folder names under Mods\\aircraft that mean the module is installed).
AIRCRAFT = {
    "Su-25T": ("Su-25T (free)", ["Su-25T"]), "TF-51D": ("TF-51D (free)", ["TF-51D"]),
    "A-10A": ("A-10A", ["A-10A"]), "A-10C": ("A-10C", ["A-10C"]), "A-10C_2": ("A-10C II", ["A-10C_2"]),
    "AJS37": ("AJS-37 Viggen", ["AJS37"]), "AV8BNA": ("AV-8B Harrier", ["AV8BNA"]),
    "Bf-109K-4": ("Bf 109 K-4", ["Bf-109K-4"]), "C-101CC": ("C-101CC", ["C-101"]), "C-130J-30": ("C-130J", ["C130J"]),
    "Christen Eagle II": ("Christen Eagle II", ["Christen Eagle II"]), "F-100D": ("F-100D", ["F-100D"]),
    "F-14A-135-GR": ("F-14A", ["F14"]), "F-14B": ("F-14B", ["F14"]), "F-14BU": ("F-14B(U)", ["F14BU"]),
    "F-15C": ("F-15C", ["F-15C"]), "F-15ESE": ("F-15E", ["F-15E"]), "F-16C_50": ("F-16C", ["F-16C"]),
    "F-4E-45MC": ("F-4E", ["F-4E"]), "F-5E-3": ("F-5E", ["F-5E", "F-5E 2024"]), "F-5E-3_FC": ("F-5E (Flaming Cliffs)", ["F-5E_FC"]),
    "F-86F Sabre": ("F-86F", ["F-86"]), "F-86F_FC": ("F-86F (Flaming Cliffs)", ["F-86_FC"]),
    "F4U-1D": ("F4U-1D Corsair", ["F4U-1D"]), "FA-18C_hornet": ("F/A-18C", ["FA-18C"]),
    "FW-190A8": ("Fw 190 A-8", ["FW-190A8"]), "FW-190D9": ("Fw 190 D-9", ["FW-190D9"]), "Hawk": ("Hawk", ["Hawk"]),
    "I-16": ("I-16", ["I-16"]), "J-11A": ("J-11A", ["J-11A"]), "JF-17": ("JF-17", ["JF-17"]),
    "L-39C": ("L-39C", ["L-39C", "L-39"]), "L-39ZA": ("L-39ZA", ["L-39ZA", "L-39"]), "La-7": ("La-7", ["La-7"]),
    "M-2000C": ("M-2000C", ["M-2000C"]), "MB-339A": ("MB-339A", ["MB-339"]),
    "MiG-15bis": ("MiG-15bis", ["MiG-15bis"]), "MiG-15bis_FC": ("MiG-15bis (Flaming Cliffs)", ["MiG-15bis_FC"]),
    "MiG-19P": ("MiG-19P", ["MiG-19P"]), "MiG-21Bis": ("MiG-21bis", ["MiG-21bis"]),
    "MiG-29 Fulcrum": ("MiG-29A (full fidelity)", ["MiG-29-Fulcrum"]), "MiG-29A": ("MiG-29A", ["MiG-29"]),
    "MiG-29S": ("MiG-29S", ["MiG-29"]), "Mirage-F1CE": ("Mirage F1CE", ["Mirage-F1"]),
    "Mirage-F1EE": ("Mirage F1EE", ["Mirage-F1"]), "MosquitoFBMkVI": ("Mosquito FB VI", ["MosquitoFBMkVI"]),
    "P-47D-30": ("P-47D", ["P-47D-30"]), "P-51D": ("P-51D", ["P-51D"]), "SpitfireLFMkIX": ("Spitfire LF Mk IX", ["SpitfireLFMkIX"]),
    "Su-25": ("Su-25", ["Su-25A"]), "Su-27": ("Su-27", ["Su-27"]), "Su-33": ("Su-33", ["Su-33"]), "Yak-52": ("Yak-52", ["Yak-52"]),
    "AH-64D_BLK_II": ("AH-64D Apache", ["AH-64D"]), "CH-47Fbl1": ("CH-47F", ["CH-47F"]),
    "Ka-50_3": ("Ka-50 III", ["Ka-50"]), "Ka-50": ("Ka-50", ["Ka-50"]), "Mi-24P": ("Mi-24P", ["Mi-24P"]),
    "Mi-8MT": ("Mi-8MTV2", ["Mi-8MTV2"]), "OH58D": ("OH-58D", ["OH-58D"]), "SA342L": ("SA342 Gazelle", ["SA342"]),
    "UH-1H": ("UH-1H Huey", ["Uh-1H"]),
}
MISSION_FILES = ("mission", "options", "warehouses", "l10n/DEFAULT/dictionary", "l10n/DEFAULT/mapResource")


def pack(folder: Path) -> None:
    """Build every map with every aircraft into one tightly packed file plus an index. The window
    unpacks the one mission the player picked; nothing is built on the player's PC."""
    import io, json, tarfile, tempfile, zipfile
    tmp = Path(tempfile.mkdtemp()) / "one.miz"
    made, skipped = {}, []
    with tarfile.open(folder / "scenes.tar.xz", "w:xz", preset=9) as tar:
        for map_key in MAPS:
            for kind in AIRCRAFT:
                try:
                    build(tmp, map_key, kind)
                except Exception as e:                       # for example: no ramp spot big enough on this map
                    skipped.append(f"{map_key}/{kind}: {type(e).__name__}: {e}")
                    continue
                made.setdefault(map_key, []).append(kind)
                with zipfile.ZipFile(tmp) as z:
                    if sorted(z.namelist()) != sorted(MISSION_FILES):
                        raise SystemExit(f"unexpected files in {map_key}/{kind}: {z.namelist()}")
                    for name in MISSION_FILES:
                        data = z.read(name)
                        item = tarfile.TarInfo(f"{map_key}/{kind}/{name}")
                        item.size = len(data)
                        tar.addfile(item, io.BytesIO(data))
    index = {"maps": {k: {"label": MAP_LABELS[k][0], "folder": MAP_LABELS[k][1], "aircraft": made[k]} for k in made},
             "aircraft": {k: {"label": v[0], "folders": v[1], "helicopter": k in helicopters.helicopter_map}
                          for k, v in AIRCRAFT.items()},
             "files": list(MISSION_FILES)}
    (folder / "scenes.json").write_text(json.dumps(index, indent=1))
    print("packed", sum(len(v) for v in made.values()), "missions,", (folder / "scenes.tar.xz").stat().st_size, "bytes")
    for line in skipped:
        print("skipped", line)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--pack"]:
        pack(Path(args[1]) if len(args) > 1 else Path(__file__).parent)
        raise SystemExit
    out = Path(args[0] if args else Path(__file__).parent / "dcstune_bench.miz")
    made = build(out, *(args[1:3]))
    print("wrote", made, made.stat().st_size, "bytes")
