"""Build mission/dcstune_bench.miz with pydcs. Free content only (Caucasus, Su-25T,
AI-flown), no weapons, no enemies, fixed weather and time, so every run is the same.

Scenes (unit names are what the hook's camera follows):
  TUNE-CITY-1  low and slow along the Batumi waterfront - dense buildings, water, trees
  TUNE-RAMP-1  taxiing/holding on a crowded Batumi ramp - many aircraft models and shadows
  TUNE-HIGH-1  at 4.4 km inside a broken cloud layer
"""
import sys
from pathlib import Path

import dcs
from dcs import cloud_presets, mapping, planes, task
from dcs.terrain import caucasus

out = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "dcstune_bench.miz")

m = dcs.Mission(terrain=caucasus.Caucasus())
m.name = "DCS Tune benchmark"
m.start_time = m.start_time.replace(month=6, day=15, hour=10, minute=0, second=0)
m.weather.clouds_preset = cloud_presets.Clouds.Broken4.value
m.weather.clouds_base = 3800
m.weather.wind_at_ground.speed = 0
m.weather.turbulence_at_ground = 0

usa = m.country("USA")
batumi = m.terrain.airports["Batumi"]
kobuleti = m.terrain.airports["Kobuleti"]
bp, kp = batumi.position, kobuleti.position


def flight(name, start, end, alt, speed_kmh, n=1, via=None):   # singletons: a pydcs 2-ship spawns 10 m apart and collides
    g = m.flight_group_inflight(usa, name, planes.Su_25T, position=start, altitude=alt,
                                speed=speed_kmh, maintask=task.Nothing, group_size=n)
    for i, u in enumerate(g.units):
        u.name = f"{name}-{i + 1}"
        u.pylons.clear()
    if via:
        g.add_waypoint(via, alt, speed_kmh)
    g.add_waypoint(end, alt, speed_kmh)
    # fly back and forth for as long as the benchmark needs
    g.add_waypoint(start, alt, speed_kmh)
    g.add_waypoint(end, alt, speed_kmh)
    return g


# 1. city: in from the sea, over Batumi, then up the flat coast (hills rise south and east)
flight("TUNE-CITY", mapping.Point(bp.x - 2000, bp.y - 7000, m.terrain),
       mapping.Point(kp.x, kp.y - 1500, m.terrain), 350, 450,
       via=mapping.Point(bp.x + 3000, bp.y + 1000, m.terrain))

# 2. airfield: one aircraft starting from the ramp, surrounded by parked ones
ramp = m.flight_group_from_airport(usa, "TUNE-RAMP", planes.Su_25T, batumi, maintask=task.Nothing,
                                   start_type=dcs.mission.StartType.Cold, group_size=1)
ramp.units[0].name = "TUNE-RAMP-1"
ramp.units[0].pylons.clear()
ramp.late_activation = False
ramp.uncontrolled = True          # sits on the ramp, engines off, never moves
for i in range(8):
    g = m.flight_group_from_airport(usa, f"TUNE-PARK-{i}", planes.Su_25T, batumi, maintask=task.Nothing,
                                    start_type=dcs.mission.StartType.Cold, group_size=1)
    g.uncontrolled = True
    g.units[0].pylons.clear()

# 3. clouds: inside the broken layer
flight("TUNE-HIGH", mapping.Point(bp.x + 20000, bp.y + 30000, m.terrain),
       mapping.Point(bp.x + 90000, bp.y + 60000, m.terrain), 4400, 750)

# One spectator-capable slot is not needed: the hook hosts and stays unslotted.
m.save(str(out))
print("wrote", out, out.stat().st_size, "bytes")
