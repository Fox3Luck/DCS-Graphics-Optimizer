# DCS Graphics Optimizer - Fox3 Managed Solutions Inc.
# Created 2026-11-18. Tests for the heat check (beta issue #23).
import json

import pytest

from dcstune import heat


def _laps(fps, lows=None, lap_sec=120):
    return [{"avg_fps": f, "p1_low_fps": (lows or fps)[i] * (1 if lows else 0.8), "t0": 1000 + i * lap_sec, "t1": 1000 + i * lap_sec + 100}
            for i, f in enumerate(fps)]


def _samples(n_laps, temp, clock=None, cpu=None, lap_sec=120):
    out = []
    for i in range(n_laps):
        for t in range(0, 100, 4):
            out.append({"t": 1000 + i * lap_sec + t, "gpu_temp": temp(i) if temp else None,
                        "gpu_clock": clock(i) if clock else None, "gpu_power": None, "cpu_speed": cpu(i) if cpu else None})
    return out


def test_a_pc_that_holds_its_frame_rate_is_steady():
    h = heat.summarize(_laps([96, 96, 95, 96, 95, 96]), _samples(6, lambda i: 60 + 2 * i, lambda i: 2700, lambda i: 118))
    assert h["verdict"] == "steady" and abs(h["drop_pct"]) < 1
    assert h["gpu_temp_start"] == 60 and h["gpu_temp_peak"] == 70
    assert [r["lap"] for r in h["laps"]] == [1, 2, 3, 4, 5, 6] and h["laps"][0]["gpu_temp"] == 60
    assert h["minutes"] == pytest.approx(11.7, abs=0.1)
    text = " ".join(h["lines"])
    assert "Verdict: steady" in text and "96 FPS" in text and "60 °C at the start, 70 °C at its hottest" in text
    assert "cooling" not in text.lower()


def test_a_hot_graphics_card_that_lowers_its_clock_is_named():
    h = heat.summarize(_laps([100, 97, 93, 90, 88, 88]), _samples(6, lambda i: 70 + 4 * i, lambda i: 2700 - 60 * i, lambda i: 118))
    assert h["verdict"] == "slows" and h["drop_pct"] == 12.0 and h["last_fps"] == 88
    assert h["gpu_clock_drop_pct"] > 4 and (h["cpu_speed_drop_pct"] or 0) == 0
    text = " ".join(h["lines"])
    assert "slows down noticeably" in text and "the graphics card lowered its clock" in text
    assert "about 88 FPS where the short test showed 100" in text
    assert "goal of about 80 FPS" in text                       # 95% of 88, rounded down to a 5
    assert "processor" not in text.split("What the readings show:")[1].split(".")[0]


def test_a_laptop_processor_that_is_slowed_is_named_without_any_graphics_readings():
    # AMD and Intel cards: no temperature from the driver. The processor speed still shows it.
    h = heat.summarize(_laps([60, 58, 57, 57, 56, 57]), _samples(6, None, None, lambda i: 110 - 5 * i))
    assert h["verdict"] == "slight" and 3 <= h["drop_pct"] < 6
    assert h["gpu_temp_peak"] is None and h["laps"][0]["gpu_temp"] is None
    text = " ".join(h["lines"])
    assert "not available on this PC" in text and "slows down a little" in text
    assert "Windows let the processor run" in text


def test_slowing_with_no_readings_still_gives_advice_and_a_hot_steady_card_is_mentioned():
    h = heat.summarize(_laps([80, 76, 74, 73, 72, 72]), [])
    assert h["verdict"] == "slows" and "do not show which part" in " ".join(h["lines"])
    hot = heat.summarize(_laps([80, 80, 80, 80]), _samples(4, lambda i: 86))
    assert hot["verdict"] == "steady" and "does run hot (86 °C)" in " ".join(hot["lines"])
    faster = heat.summarize(_laps([80, 81, 82, 82]), [])                 # got faster: steady, worded "up"
    assert faster["verdict"] == "steady" and "(up " in faster["lines"][0]
    with pytest.raises(ValueError):
        heat.summarize(_laps([80, 80]), [])
    json.dumps(h)                                                          # goes to the window as JSON


def test_a_graphics_driver_reset_is_recognized_in_the_dcs_log(tmp_path):
    # Test PC, 2026-11-18: the driver reset under DCS, DCS showed a crash box, and the test waited
    # ten minutes and then blamed a slow start. The log says what happened; read it.
    from dcstune import bench
    b = bench.Bench.__new__(bench.Bench)
    b.profile_dir = tmp_path
    (tmp_path / "Logs").mkdir()
    assert not b._graphics_reset()                                  # no log at all
    log = tmp_path / "Logs" / "dcs.log"
    log.write_text("2026-11-18 21:16:16.421 INFO    DCSTUNE (Main): scene 3 'clouds' start\n" * 50)
    assert not b._graphics_reset()
    with open(log, "a") as f:
        f.write("2026-11-18 21:16:52.171 ERROR   DX11BACKEND (7992): DX device removed. Reason: 0x887A0006\n")
    assert b._graphics_reset()
    assert "graphics driver stopped" in bench.GRAPHICS_RESET and "settings have been put back" in bench.GRAPHICS_RESET
