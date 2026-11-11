# DCS Graphics Optimizer — beta tester notes

Thank you for trying this. It is a beta: it has been tested thoroughly on one PC and needs to be tried on others.

## What it does
It rates your PC and your DCS graphics settings, tests them in real DCS, and recommends settings that hold your monitor's refresh rate in the worst moments. Nothing is changed until you press **Apply**, and **Undo last change** puts your previous settings back.

## Before you start
- Windows 10 or 11, DCS World 2.9 (standalone or Steam), flat screen. If VR is switched on in DCS, the scorecard rates your VR settings as a rough estimate; the tests still run on the monitor and leave your VR settings alone.
- Close DCS and anything else that uses the graphics card (other games, video renders, AI tools).
- Plan to leave the PC alone during a test: 10 to 20 minutes for the normal test, 35 to 60 for the thorough one.

## Steps
1. Download `DCSGraphicsOptimizer.exe` and double-click it. There is nothing to install.
2. If Windows shows a warning, note exactly what it says and which publisher it names (it should be Fox3 Managed Solutions Inc.), then choose to run it.
3. Read the scorecard, then press **Test and optimize**. DCS will start and close by itself several times.
4. Read the result. Press **Apply these settings** if you want them, fly a mission you know well, and press **Undo last change** if you do not like them.

## What to send back
If you answered yes to anonymous results, the test data reaches us by itself; the items below are still welcome, especially screenshots and anything that went wrong.
- The report folder: `Saved Games\DCS\DCS Graphics Optimizer Reports\report-<date>-<time>` (zip it). It contains the report page, screenshots and `audit.json`: your CPU, graphics card, memory, monitor, DCS version, VR headset and VR software if any, your graphics and VR settings, and the test results. It contains no names, folder paths or account details.
- Any Windows warning you saw when starting the exe.
- Whether the recommended settings felt better, worse or the same in your normal flying.
- Anything that went wrong: DCS not starting, the test stopping, settings not put back.

## If something goes wrong
- Start the tool again: if a test was interrupted it restores your original settings by itself and tells you.
- Your original file is also kept next to `options.lua` in `Saved Games\DCS\Config` as `options.lua.dcstune-bak-<date>-<time>`.

## Anonymous results (your choice)
The first time you start it, the tool asks whether it may send the result of each test to Fox3. It is anonymous: hardware, DCS version, VR headset, settings and frame rates, with no names, accounts, folder names or screenshots, and stored without your internet address. It explains this on screen. If you say yes, you can also add a comment to a result from inside the tool, and you do not need to send the report folder unless we ask. If you say no, nothing is sent over the internet and the tool works the same.
