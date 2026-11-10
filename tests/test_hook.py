"""Run the real hook file inside a Lua VM with DCS's functions mocked, to prove the
state machine: consume directive -> host -> wait for world -> settle -> scenes ->
result JSON -> exit. (Real-game behaviour is verified separately on the test box.)"""
import json
from pathlib import Path

import pytest

lupa = pytest.importorskip("lupa")
from dcstune.bench import SCENES, parse_result

HOOK = Path(__file__).resolve().parent.parent / "hook" / "dcstune_bench.lua"

HARNESS = r"""
local W = ...            -- python-provided world
log = { INFO = 1, write = function(tag, lvl, msg) W.logs(msg) end }
lfs = { writedir = function() return W.dir end }
local wall = 0
os.time = function() return math.floor(wall) end
os.clock = function() return wall end
net = {
  json2lua = function(s) return W.json2lua(s) end,
  get_default_server_settings = function() return { advanced = {} } end,
  start_server = function(cfg) W.started(cfg.isPublic, cfg.password, cfg.missionList[1]); return true end,
  stop_network = function() W.netstop() end,
  dostring_in = function(state, code)
    local name = code:match('UnitName == "([^"]+)"')
    if not W.world_up or not name or (W.missing and name == W.missing) then return '' end
    return string.format('%.2f %.2f %.2f %.4f', 1000 + wall * 120, 300, 5000, 0.5)
  end,
}
Export = { LoSetCommand = function(c) W.cmd(c) end,
           LoSetCameraPosition = function(p) W.cam(p.p.x, p.p.y, p.p.z, p.x.x, p.x.y, p.x.z) end }
local cb
package.preload['Options.Data'] = function()
  return { setGraphics = function(k, v) W.setopt(k, v) end, saveChanges = function() W.saved() end }
end
DCS = { getRealTime = function() return wall end, setPause = function() end,
        stopMission = function() W.stopreq() end,
        makeScreenShot = function(n) W.shot(n) end,
        exitProcess = function() W.exited() end,
        setUserCallbacks = function(t) cb = t end }
return function(src) local f = assert(load(src, "hook")); f(); return cb end,
       function(dt) wall = wall + dt end
"""


class World:
    def __init__(self, tmp, missing=None):
        self.dir = str(tmp) + "\\"
        self.world_up, self.missing = False, missing
        self.log, self.cams, self.shots, self.cmds = [], [], [], []
        self.exit, self.server = False, None
        self.starts, self.stop_requested, self.opts, self.saves, self.netstops = 0, False, [], 0, 0

    def logs(self, m): self.log.append(str(m))
    def started(self, public, pw, miz):
        self.server = (public, pw, miz); self.starts += 1; self.pending_start = True
    def stopreq(self): self.stop_requested = True
    def setopt(self, k, v): self.opts.append((self.starts, k, v))
    def saved(self): self.saves += 1
    def netstop(self): self.netstops += 1
    def cmd(self, c): self.cmds.append(c)
    def cam(self, *a): self.cams.append(a)
    def shot(self, n): self.shots.append(n)
    def exited(self): self.exit = True


def _run(tmp_path, monkeypatch, directive, missing=None, fps=100, max_seconds=400):
    (tmp_path / "Config").mkdir()
    # the hook builds Windows paths; map them onto the temp dir
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    w = World(tmp_path, missing)
    w.json2lua = lambda s: lua.eval("function(j) return j end")(_to_lua(lua, json.loads(s)))
    files = {}
    real = {w.dir + "Config\\dcstune_directive.json": tmp_path / "Config" / "dcstune_directive.json",
            w.dir + "Config\\dcstune_result.json": tmp_path / "Config" / "dcstune_result.json"}
    if directive is not None:
        real[w.dir + "Config\\dcstune_directive.json"].write_text(json.dumps(directive))
    lua.globals().py_open = lambda p, mode: _open(lua, real, p, mode)
    lua.globals().py_remove = lambda p: real[p].unlink()
    lua.execute("io.open = function(p, m) return py_open(p, m) end; os.remove = function(p) py_remove(p) end")
    load, tick = lua.execute(HARNESS, w)
    cb = load(HOOK.read_text())
    if cb is None:
        return w, None, real
    dt, t = 1.0 / fps, 0.0
    start_at = None
    while not w.exit and t < max_seconds:
        tick(dt); t += dt
        if getattr(w, "pending_start", False):          # mission takes ~3 s to load
            w.pending_start, start_at = False, t + 3
        if start_at and t >= start_at:
            start_at = None
            cb.onSimulationStart()
            w.world_up = True
        if w.stop_requested:                             # DCS.stopMission ends the mission
            w.stop_requested, w.world_up = False, False
            cb.onSimulationStop()
        cb.onSimulationFrame()
    res = real[w.dir + "Config\\dcstune_result.json"]
    return w, json.loads(res.read_text()) if res.exists() else None, real


def _to_lua(lua, obj):
    if isinstance(obj, dict):
        return lua.table_from({k: _to_lua(lua, v) for k, v in obj.items()})
    if isinstance(obj, list):
        return lua.table_from([_to_lua(lua, v) for v in obj])
    return obj


def _open(lua, real, path, mode):
    p = real.get(path)
    if p is None or ("r" in mode and not p.exists()):
        return None
    if "r" in mode:
        text = p.read_text()
        return lua.table_from({"read": lambda self, fmt: text, "close": lambda self: None})
    buf = []
    return lua.table_from({"write": lambda self, s: buf.append(s),
                           "close": lambda self: p.write_text("".join(buf))})


DIRECTIVE = {"mission": "C:\\x\\dcstune_bench.miz", "scenes": SCENES, "tag": "t1",
             "scene_sec": 5, "settle_sec": 3, "scene_lead_sec": 1}


def test_inert_without_directive(tmp_path, monkeypatch):
    w, result, _ = _run(tmp_path, monkeypatch, None)
    assert result is None and w.server is None and "inert" in w.log[-1]


def test_full_run(tmp_path, monkeypatch):
    w, raw, real = _run(tmp_path, monkeypatch, DIRECTIVE)
    assert not (tmp_path / "Config" / "dcstune_directive.json").exists()      # consumed on read
    public, password, miz = w.server
    assert public is False and len(password) == 10 and miz == DIRECTIVE["mission"]
    assert w.exit and raw["ok"] is True and raw["clock"] == "DCS.getRealTime"
    assert [s["name"] for s in raw["scenes"]] == ["city", "airfield", "clouds"]
    parsed = parse_result(raw)
    for s in parsed["scenes"]:
        assert 480 <= s["frames"] <= 500            # 5 s at 100 fps, lead-in excluded
        assert s["avg_fps"] == pytest.approx(100, rel=0.01) and s["stutters"] == 0
    assert w.shots == ["dcstune_t1_city", "dcstune_t1_airfield", "dcstune_t1_clouds"]
    assert w.cmds == [16]
    # camera sits behind and above a moving subject and looks at it
    px, py, pz, fx, fy, fz = w.cams[-1]
    assert py > 300 and fx > 0 and fy < 0


def test_missing_unit_fails_cleanly(tmp_path, monkeypatch):
    w, raw, _ = _run(tmp_path, monkeypatch, DIRECTIVE, missing="TUNE-RAMP-1")
    assert w.exit and raw["ok"] is False and "TUNE-RAMP-1" in raw["reason"]
    with pytest.raises(Exception, match="unit not found"):
        parse_result(raw)


def test_never_starting_mission_times_out(tmp_path, monkeypatch):
    d = dict(DIRECTIVE, start_timeout=20, total_timeout=60)
    w, raw, _ = _run(tmp_path, monkeypatch, d, missing="TUNE-CITY-1", fps=30)
    assert w.exit and raw["ok"] is False


def test_several_trials_in_one_launch(tmp_path, monkeypatch):
    d = dict(DIRECTIVE, total_timeout=300, trials=[
        {"tag": "a"},
        {"tag": "b", "set": {"shadows": 0, "clouds": 0}},
        {"tag": "c", "set": {"shadows": 4, "clouds": 3}}])
    w, raw, _ = _run(tmp_path, monkeypatch, d)
    assert w.exit and raw["ok"] is True
    assert w.starts == 3 and w.netstops == 2            # one DCS process, three mission starts
    assert [t["tag"] for t in raw["trials"]] == ["a", "b", "c"]
    assert raw["trials"][0]["applied"] == "unchanged" and raw["trials"][1]["applied"] == "clouds=0 shadows=0"
    # options are set BEFORE the mission of that trial starts, never during the first one
    assert sorted(w.opts) == [(1, "clouds", 0), (1, "shadows", 0), (2, "clouds", 3), (2, "shadows", 4)]
    assert w.saves == 2
    for t in raw["trials"]:
        assert [s["name"] for s in t["scenes"]] == ["city", "airfield", "clouds"]
        assert all(len(s["frame_ms"]) > 400 for s in t["scenes"])
    assert raw["scenes"] == raw["trials"][0]["scenes"]
    assert "dcstune_b_city" in w.shots and "dcstune_a_clouds" in w.shots
