-- dcstune_bench.lua -- DCS Graphics Optimizer benchmark driver (Saved Games\<profile>\Scripts\Hooks)
--
-- Inert unless Config\dcstune_directive.json exists. The directive is deleted the
-- moment it is read, so a crash or a manual DCS launch can never replay a benchmark.
-- Flow: host the bundled mission locally (unlisted, random password), never slot,
-- fly a free camera behind named AI aircraft for each scene, time every rendered
-- frame, write Config\dcstune_result.json, exit DCS.
-- Log lines: grep "DCSTUNE" in dcs.log.

local function L(msg) log.write("DCSTUNE", log.INFO, tostring(msg)) end

local DIRECTIVE = lfs.writedir() .. "Config\\dcstune_directive.json"
local RESULT    = lfs.writedir() .. "Config\\dcstune_result.json"

local D
do
  local f = io.open(DIRECTIVE, "r")
  if f then
    local raw = f:read("*a"); f:close()
    os.remove(DIRECTIVE)
    local ok, tbl = pcall(net.json2lua, raw)
    if ok and type(tbl) == "table" and type(tbl.scenes) == "table" then D = tbl
    else L("directive parse failed") end
  end
end
if not D then L("no directive -- hook inert"); return end
L("directive loaded: mission=" .. tostring(D.mission) .. " scenes=" .. #D.scenes)

local cfg = {
  settle_sec    = tonumber(D.settle_sec) or 20,   -- texture streaming after the world appears
  scene_sec     = tonumber(D.scene_sec) or 25,
  scene_lead    = tonumber(D.scene_lead_sec) or 4, -- untimed seconds after each camera move
  view_cmd      = tonumber(D.view_cmd) or 16,
  start_timeout = tonumber(D.start_timeout) or 120,
  total_timeout = tonumber(D.total_timeout) or 600,
  screenshots   = D.screenshots ~= false,
  tag           = tostring(D.tag or "run"),
}

local function now()
  if DCS.getRealTime then return DCS.getRealTime() end
  return os.clock()
end

local state = {
  t0 = os.time(), frames = 0, hosted = false, running = false, finished = false,
  ready_at = nil, scene_i = 0, scene_t0 = nil, last = nil, results = {},
  subj = nil, subj_t = 0, vel = { x = 0, y = 0, z = 0 }, fwd = { x = 1, z = 0 },
}

local function writeResult(ok, reason)
  local parts = {}
  for _, r in ipairs(state.results) do
    parts[#parts + 1] = string.format('{"name":"%s","shot":"%s","frame_ms":[%s]}',
      r.name, r.shot or "", table.concat(r.ms, ","))
  end
  local f = io.open(RESULT, "w")
  if f then
    f:write(string.format('{"ok":%s,"reason":"%s","tag":"%s","clock":"%s","scenes":[%s]}',
      tostring(ok), tostring(reason or ""), cfg.tag,
      DCS.getRealTime and "DCS.getRealTime" or "os.clock", table.concat(parts, ",")))
    f:close()
  end
  L("result written ok=" .. tostring(ok) .. " reason=" .. tostring(reason or ""))
end

local function finish(ok, reason)
  if state.finished then return end
  state.finished = true
  writeResult(ok, reason)
  pcall(function() DCS.exitProcess() end)
end

local function tryHost()
  state.hosted = true
  if type(net.start_server) ~= "function" then finish(false, "net.start_server missing"); return end
  local scfg
  if type(net.get_default_server_settings) == "function" then
    local ok1, c1 = pcall(function() return net.get_default_server_settings(D.mission) end)
    if ok1 and type(c1) == "table" then scfg = c1 else
      local ok2, c2 = pcall(function() return net.get_default_server_settings() end)
      if ok2 and type(c2) == "table" then scfg = c2 end
    end
  end
  if type(scfg) ~= "table" then scfg = {} end
  if type(scfg["advanced"]) == "table" then
    scfg["advanced"]["resume_mode"] = 1
    scfg["advanced"]["pause_on_load"] = false
    scfg["advanced"]["external_views"] = true
    scfg["advanced"]["allow_external_views"] = true
    scfg["advanced"]["allow_object_export"] = true
  end
  scfg["missionList"]    = { D.mission }
  scfg["listStartIndex"] = 1
  scfg["port"]           = tonumber(D.port) or 10319
  scfg["name"]           = "DCSTUNE-LOCAL-BENCH"
  scfg["isPublic"]       = false   -- never advertised; exists only because hooks cannot start single-player
  pcall(function() math.randomseed(os.time() + math.floor((os.clock() or 0) * 1000)) end)
  scfg["password"]       = string.format("dt%08x", math.random(0, 0x7fffffff))
  scfg["maxPlayers"]     = 1
  scfg["require_pure_clients"] = false
  local ok, ret = pcall(function() return net.start_server(scfg) end)
  L("net.start_server ok=" .. tostring(ok) .. " ret=" .. tostring(ret))
  if not ok then finish(false, "start_server failed") end
end

-- Position + heading of a named AI unit from the export state. Polled a few times a
-- second only (it walks the world-object list); the camera is extrapolated in between
-- so the per-frame cost of the benchmark itself stays negligible.
local function pollSubject(unitName)
  local code = string.format([[
    local objs = LoGetWorldObjects()
    if objs then
      for _, o in pairs(objs) do
        if o and o.UnitName == %q and o.Position then
          return string.format('%%.2f %%.2f %%.2f %%.4f', o.Position.x, o.Position.y, o.Position.z, o.Heading or 0)
        end
      end
    end
    return ''
  ]], unitName)
  local ok, s = pcall(function() return net.dostring_in("export", code) end)
  if not ok or type(s) ~= "string" or s == "" then return nil end
  local x, y, z, h = s:match("([-%d%.]+) ([-%d%.]+) ([-%d%.]+) ([-%d%.]+)")
  if not x then return nil end
  return { x = tonumber(x), y = tonumber(y), z = tonumber(z), h = tonumber(h) }
end

local function updateSubject(scene, t)
  local p = pollSubject(scene.unit)
  if not p then return false end
  if state.subj and t > state.subj_t then
    local dt = t - state.subj_t
    state.vel = { x = (p.x - state.subj.x) / dt, y = (p.y - state.subj.y) / dt, z = (p.z - state.subj.z) / dt }
  end
  state.subj, state.subj_t = p, t
  state.fwd = { x = math.cos(p.h), z = math.sin(p.h) }   -- DCS: x north, z east, heading from north
  return true
end

local function setCamera(scene, t)
  local s = state.subj
  if not s then return end
  local dt = t - state.subj_t
  local ax, ay, az = s.x + state.vel.x * dt, s.y + state.vel.y * dt, s.z + state.vel.z * dt
  local back, up, side = tonumber(scene.back) or 30, tonumber(scene.up) or 6, tonumber(scene.side) or 0
  local fwx, fwz = state.fwd.x, state.fwd.z
  local px = ax - fwx * back - fwz * side
  local pz = az - fwz * back + fwx * side
  local py = ay + up
  local fx, fy, fz = ax - px, ay - py, az - pz
  local fl = math.sqrt(fx * fx + fy * fy + fz * fz)
  if fl < 0.01 then return end
  fx, fy, fz = fx / fl, fy / fl, fz / fl
  local rx, rz = -fz, fx
  local rl = math.sqrt(rx * rx + rz * rz)
  if rl < 0.001 then rx, rz, rl = 1, 0, 1 end
  rx, rz = rx / rl, rz / rl
  local ux, uy, uz = -rz * fy, rz * fx - rx * fz, rx * fy
  pcall(function()
    Export.LoSetCameraPosition({
      x = { x = fx, y = fy, z = fz }, y = { x = ux, y = uy, z = uz },
      z = { x = rx, y = 0, z = rz },  p = { x = px, y = py, z = pz } })
  end)
end

local function startScene(i, t)
  state.scene_i, state.scene_t0, state.last = i, t, nil
  state.subj, state.vel = nil, { x = 0, y = 0, z = 0 }
  local scene = D.scenes[i]
  state.results[i] = { name = tostring(scene.name), ms = {} }
  if not updateSubject(scene, t) then finish(false, "unit not found: " .. tostring(scene.unit)); return end
  L("scene " .. i .. " '" .. tostring(scene.name) .. "' start")
end

local function endScene(t)
  local i = state.scene_i
  local r = state.results[i]
  L(string.format("scene %d done: %d frames", i, #r.ms))
  if cfg.screenshots then
    r.shot = string.format("dcstune_%s_%s", cfg.tag, r.name)
    pcall(function() DCS.makeScreenShot(r.shot) end)
  end
  if i >= #D.scenes then finish(true, "") else startScene(i + 1, t) end
end

local h = {}

function h.onSimulationStart()
  state.running = true
  L("simulation started")
end

function h.onSimulationStop()
  if not state.finished then finish(false, "simulation stopped early") end
end

function h.onSimulationFrame()
  if state.finished then return end
  state.frames = state.frames + 1
  local elapsed = os.time() - state.t0
  if elapsed > cfg.total_timeout then finish(false, "total timeout"); return end
  if not state.hosted then
    if state.frames == 30 then tryHost() end
    return
  end
  if not state.running then
    if elapsed > cfg.start_timeout then finish(false, "mission never started (not logged in, or mission failed to load?)") end
    return
  end

  local t = now()
  if not state.ready_at then
    -- wait for the first AI unit to exist, then let textures stream in
    if state.frames % 30 == 0 and pollSubject(D.scenes[1].unit) then
      state.ready_at = t + cfg.settle_sec
      pcall(function() DCS.setPause(false) end)
      pcall(function() Export.LoSetCommand(cfg.view_cmd) end)
      updateSubject(D.scenes[1], t)
      L("world up; settling " .. cfg.settle_sec .. "s")
    elseif elapsed > cfg.start_timeout then
      local okd, names = pcall(function() return net.dostring_in("export", [[
        local t, n = {}, 0
        local objs = LoGetWorldObjects()
        if not objs then return 'LoGetWorldObjects=nil' end
        for _, o in pairs(objs) do
          n = n + 1
          if n <= 30 and o then t[#t+1] = tostring(o.Name) .. '/' .. tostring(o.UnitName) end
        end
        return 'count=' .. n .. ' ' .. table.concat(t, ', ')
      ]]) end)
      L("world objects seen: " .. tostring(okd) .. " " .. tostring(names))
      finish(false, "benchmark aircraft never appeared")
    end
    return
  end
  if state.scene_i == 0 then
    setCamera(D.scenes[1], t)
    if t >= state.ready_at then startScene(1, t) end
    return
  end

  local scene = D.scenes[state.scene_i]
  if state.frames % 12 == 0 then updateSubject(scene, t) end
  setCamera(scene, t)
  local since = t - state.scene_t0
  if since >= cfg.scene_lead then
    if state.last then
      local ms = state.results[state.scene_i].ms
      ms[#ms + 1] = string.format("%.3f", (t - state.last) * 1000)
    end
    state.last = t
  end
  if since >= cfg.scene_lead + cfg.scene_sec then endScene(t) end
end

DCS.setUserCallbacks(h)
L("armed")
