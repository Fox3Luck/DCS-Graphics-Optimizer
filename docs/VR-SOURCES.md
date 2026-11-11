# VR tuning — sources of truth

Collected 2026-11-11 for the VR version of DCS Graphics Optimizer. Ranked by how far each
can be trusted. "Read on the test box" means read directly from the files of DCS 2.9.31 and
Pimax Play 1.42 on the development PC, not from a web page.

## 1. DCS itself (highest trust — read on the test box)

`MissionEditor\modules\Options\optionsDb.lua` defines every option, its legal range and
DCS's own **VR preset**.

VR section (`options.lua` → `VR`):

| Option | Range / type | Default | DCS VR preset |
|---|---|---|---|
| `enable` | checkbox | false | true |
| `pixel_density` | slider 0.5 – 2.5 | 1.0 | 1.0 |
| `msaaMaskSize` | slider 0.1 – 1.0 | 0.42 | 0.42 |
| `bloom` | checkbox | true | true |
| `enableHMDMask` | checkbox | true | true |
| `openxr_quadView` | checkbox | false | true |
| `openxr_eyeGaze` | checkbox | false | true |
| `mirror_source`, `mirror_crop`, `mirror_use_DCS_resolution` | desktop mirror only | | |

Graphics values in ED's VR preset (what ED considers a sane VR starting point):
textures Medium (1), terrain textures Low (`min`), shadows Medium (3), flat terrain shadows
Flat (1), clouds Standard (1), visibility Medium, water Medium (1), civ traffic Low,
AA **OFF**, SSAO/SSLR/SSS off, cockpit GI off, heat blur off, forest distance 0.5,
grass 750 m, preload radius 100000, chimney smoke 0, max FPS 180.

Other slider ranges confirmed there: `Scaling` 0.5 – 0.9, `forestDistanceFactor` 0.3 – 1,
`clutterMaxDistance` 0 – 1500, `preloadRadius` 100 – 150000, `maxFPS` 30 – 300,
`LODmult` 0.1 – 2.0.

Already verified in real DCS by this project: options set through `optionsEditor.setOption`
in the hook apply at the next mission start without restarting DCS. **Not yet verified for
`VR.*` keys** — needs the headset.

## 2. The headset's own software (high trust — read on the test box)

- OpenXR active runtime: registry `HKLM\SOFTWARE\Khronos\OpenXR\1` → `ActiveRuntime`
  = `C:\Program Files\Pimax\Runtime\PiOpenXR_64.json`. This tells the tool which vendor's
  runtime DCS will use, for any brand.
- `C:\Program Files\Pimax\Runtime\P3CONFIG.json` maps Pimax model codes to names:
  `P3C9` = Crystal Light, `P3C10` = Crystal Super, `P3B` = Crystal (original).
- `%LOCALAPPDATA%\Pimax\runtime\profile.json` (last written 2025-08-28) on the test box:
  - `"Pimax P3C9"` → the headset used on this PC is a **Crystal Light**
  - `pixels_per_display_pixel_rate: 0.825` → our reading: Pimax Play render quality ≈ 0.82
    (inference from the name; to confirm by changing the slider and re-reading)
  - `enable_foveated_rendering: 1`, `gpu_upscaling_sharpness: 0.2`, `ipd: 0.058`
- No OpenXR API layers are installed (no OpenXR Toolkit, no mbucchia Quad-Views-Foveated).
- Refresh rate is **not** in any file found so far; to be read from a real run.

## 3. Pimax official guidance (vendor — trust for Pimax-specific switches)

Headset facts (pimax.com comparison pages):
- Crystal Light: 2880 × 2880 per eye, 72 / 90 / 120 Hz, **no eye tracking** (fixed foveation only).
- Crystal Super (QLED): 3840 × 3840 per eye, 72 / 90 Hz on current pages (older pages say 120).
- Crystal (original): eye tracking, 72 / 90 / 120 Hz.

"Crystal Super: the ultimate DCS setup guide":
- Pimax Play: refresh 90 Hz for tier 1–2 GPUs, 72 Hz for tier 3; render resolution 100% /
  100% / 75%; **uncheck Central Priority Rendering**; tick **Pimax OpenXR Quadviews**.
- DCS VR tab: pixel density **1.0** ("Crystal doesn't require oversampling"), bloom **off**
  (interferes with quad views), Use Quad Views **on**, Eye Tracking on.
- DCS graphics by tier (1 / 2 / 3): AA DLAA with DLSS Quality / Balanced / Performance;
  textures High / Medium / Medium; shadows High / Medium / Medium; clouds Ultra / High /
  Medium; grass, forest, scenery, preload 100% / 50% / 25–0%; SSAO+SSLR on / off / off;
  lens effects, motion blur, depth of field off for all; max FPS = headset refresh.
  Non-NVIDIA: MSAA with FSR or NIS.
- Claimed result on RTX 4090 + i9-13900KF: 80–90 FPS.

"Crystal Light optimization guide for DCS by GPU" (updated 2024-07-08; older):
- Refresh 72 Hz, render resolution at maximum, quad views on.
- "For DCS 60 to 90 frames per second works well."
- QuadViews Companion: foveated resolution 150% (4090), 100% (3080 / 4060 Ti), 75% (3060 Ti);
  peripheral 5%; sharpness 80%; transition 20%.

"Crystal Light vs Super by GPU tier, 2025 edition" (Pimax's own measurements):
- RTX 3080 + i7-12700F, Crystal Light, render quality 1, no foveation: ~50 FPS at 90 Hz, GPU 97%.
- RTX 4090 + i9-12900KF, render quality 1, no foveation: 101 FPS at 120 Hz, GPU 92%;
  with fixed foveation 119.67 FPS at GPU 80%; with quad views GPU 61%.

## 4. Quad-Views-Foveated by mbucchia (tool author — trust for how quad views behaves)

- DCS must use OpenXR. Enable "Use Quad Views" in DCS; **turn off Bloom and Lens Effects**
  (poor visuals with foveation). DCS's own Eye Tracking toggle has no effect with this layer.
- Works without eye tracking as fixed foveation (Reverb G2, Index, Quest 2/3, Beyond);
  with eye tracking on Quest Pro, Pimax Crystal / Crystal Super, Varjo, Vive Pro Eye.
- **Foveation only helps when the graphics card is the limit; if the processor is the limit
  it "will only make things worse".** This is the rule the optimizer must respect.
- Settings: `focus_multiplier`, `peripheral_multiplier` (1.0 = full resolution),
  `horizontal_focus_section` / `vertical_focus_section` (0.1 – 0.9). User overrides live in a
  `settings.cfg` under LocalAppData.

## 5. Community (lowest trust — use for hypotheses, then measure)

- Launch switches `--force_enable_VR --force_OpenXR` are widely quoted; users disagree
  whether they are still needed (the multithreaded build always uses OpenXR; the VR checkbox
  replaces the first). **Not documented by ED; to verify on the headset.**
- MSAA mask size: sources contradict each other (limits MSAA to the centre of the view /
  only affects the desktop mirror / "does not seem to work"). **Treat as unknown; measure.**
- RTX 4080 starting points quoted: render quality 0.65–0.85, pixel density 1.0, 90 Hz.
- Community practice often prefers mbucchia's layer over Pimax's built-in quad views, with
  Pimax's Quadviews and Central Priority Rendering unticked.

## What every source agrees on

1. Leave DCS pixel density at 1.0 on high-resolution headsets; lower the headset software's
   render quality instead of stacking two scalers.
2. Foveated rendering (quad views) is the biggest single lever on a Pimax, but only when the
   graphics card is the limit.
3. Bloom, lens effects, motion blur and depth of field off in VR.
4. The goal is the headset's refresh rate (72 / 90 / 120), and 60–90 is considered good.
5. DLSS/DLAA on NVIDIA; MSAA with FSR or NIS elsewhere.

## Still unknown — only the headset can answer

- Does DCS start in VR unattended from our scheduled task, and with which switches?
- Does the hook's frame timer report the headset's real rate, and how do Smart Smoothing /
  half-rate lock show up in it?
- Do `VR.*` options apply at mission restart like graphics options do?
- What does MSAA mask size really cost?
- Where Pimax Play stores refresh rate and per-game settings, and whether changing
  `profile.json` is safe (the tool may need to *recommend* Pimax Play changes, not make them).

## Links

- Pimax Crystal Super DCS guide: https://pimax.com/pages/pimax-crystal-super-the-ultimate-dcs-setup-guide
- Pimax Crystal Light DCS guide by GPU: https://store.pimax.com/blogs/crystal-light-tutorials/crystal-light-optimization-guide-for-dcs-based-on-the-gpu-that-you-have-rtx-3060-ti-rtx-3080-rtx-4060-ti-and-rtx-4090
- Pimax Light vs Super by GPU tier (2025): https://store.pimax.com/blogs/highlights/pimax-crystal-light-and-super-optimal-pairings-for-different-gpu-tiers-in-dcs-world-2025-edition
- Pimax model comparison: https://pimax.com/pages/pimax-crystal-series-comparison-crystal-og-light-super
- Pimax quad views article: https://pimax.com/quad-views-foveated-rendering-for-pimax-crystal
- Quad-Views-Foveated wiki: https://github.com/mbucchia/Quad-Views-Foveated/wiki and its DCS World page
- QuadViews Companion: https://www.digitalcombatsimulator.com/en/files/3332882/
- ED forum, Pimax settings per GPU: https://forum.dcs.world/topic/343082-dcs-best-settings-for-pimax-headsets-per-gpu/
- ED forum, Crystal Light settings: https://forum.dcs.world/topic/378921-need-advices-about-pimax-crystal-light-settings-with-dcs-yes-another-one/
- ED forum, native OpenXR thread: https://forum.dcs.world/topic/318004-dcs-now-supports-openxr-natively/
- ED forum, HMD mask / bloom explained: https://forum.dcs.world/topic/312885-what-is-the-purpose-of-settings-hmd-mask-dcs-system-resolution-bloom-effect-and-use-build-in-audio/
- Community guide by GPU: https://simracingcockpit.gg/pimax-crystal-settings-guide-a-complete-guide-sorted-by-gpu/
