# Super 8 Film Scanner Refinement: Design

Date: 2026-10-27
Status: Draft for review

## Goal

Turn the current prototype (3D-printed frame, Pi, Marlin/RAMPS-style board, loose scripts) into a more complete, cleaner device: an enclosed scanner with a web app that saves aligned, uncropped frames and nothing else; MP4 is encoded on a computer. Keep cost low and parts modern and accessible.

## Decisions

| Topic | Decision |
|---|---|
| Scope | Enclosure and mechanics, electronics, software app, lighting and image quality |
| Output | Aligned, uncropped frame sequence only (PNG or JPEG); MP4 is encoded on a computer with `tools/encode_reel.py`. User decision: the device does not encode video |
| Look | Denoise and resize are off by default (opt-in). Sprocket hole and film edges stay in frame |
| Interface | Web UI served by the Pi over Wi-Fi/LAN. No built-in screen in v1 |
| Controller | Small custom RP2040 board with 2x TMC2209, LED driver, sensor input. Prototype first on off-the-shelf modules |
| Camera | Raspberry Pi HQ Camera (IMX477), `picamera2`, Pi 4 or Pi 5 |
| Lens | Same lens as the original build: Pimoroni microscope lens, 0.12-1.8x (C-mount, no adapters). Chosen for cost; sharper enlarger lenses are a later upgrade |
| Cost target | Cheapest-build column: about $230 |
| Licence | Refines existing GPL-3.0 code. A clean-room rewrite is a separate decision if a commercial licence is wanted |

## Architecture

Three layers:

1. **Controller board (RP2040)** drives two steppers and the LED. It takes plain serial commands from the Pi and replies when each move completes.
2. **Scanner app (Pi)** is one Python service: camera, alignment, scan loop, file output, web server.
3. **Web UI (browser)** has live preview, exposure and light controls, Start/Stop/Pause, progress, and a "Test frame" button that captures and aligns one frame.

Repo layout: `app/`, `firmware/`, `hardware/` (CAD and PCB), `legacy/` (existing scripts, kept).

## Hardware

**Enclosure and mechanics (3D-printed)**
- Projector-style film path: feed reel, tension arm, guide rollers, film gate (camera and light), sprocket and rubber-wheel drive, take-up reel. Supports 3" to 7" reels.
- Printed case encloses Pi, board and wiring. Exposed: reels, film path, power inlet. Back panel: USB storage port and Ethernet.
- The gate is flat and wide enough to keep the sprocket hole and edges in frame, with no moving parts on the image side.
- Existing FreeCAD parts are updated or replaced. The camera mount stays close to the original (the microscope lens screws straight onto the HQ camera), with room for focus and zoom adjustment. Before editing, check how the current parts map onto the new layout.

**Lighting.** 95+ CRI white LED, constant-current driver, PWM dimming from the controller, opal diffuser behind the film gate. Light and exposure are fixed during a scan.

**Controller board.** RP2040, 2x TMC2209, one LED driver channel, one sensor input, 12 V in with a buck converter to 5 V. Prototype on perfboard with off-the-shelf modules, then a small two-layer PCB.

**Camera.** Pi HQ Camera (IMX477, about 3,200 px across the frame including the sprocket hole, more than the film holds). Lens is the original microscope zoom; set zoom and focus once for the frame and lock them. Test for the sharpest aperture setting. Save the highest-quality JPEG or PNG, optional RAW DNG.

## Controller protocol (Pi to RP2040, serial)

Commands: `ADVANCE <steps>`, `WIND <steps>`, `LIGHT <0-100>`, `STATUS`. The board replies when a move finishes. A timeout or error response pauses the scan.

## Software

Modules in `app/`:
- `controller.py`: serial wrapper (`advance`, `wind`, `set_light`, `status`). Blocks until the board confirms.
- `camera.py`: `picamera2` wrapper, fixed exposure, gain and white balance, full-resolution capture and a small preview stream.
- `align.py`: finds the sprocket hole with OpenCV and returns the shift to a fixed position. Pure function, image in and offset out. Reuses existing detection logic.
- `scan.py`: the loop (advance, capture, align, save, update progress). Pause, stop, and resume from the saved frame count.
- `server.py`: FastAPI app serving the page, preview and control endpoints.

**Alignment.** Each frame is translated so the sprocket hole sits at the same pixel position. Area shifted in from outside the capture is filled black. Nothing is cropped.

**Scan loop details (from the legacy script).** After each advance, if the hole is more than 3% of the image height from the target row, the film is nudged (forward 15 steps or back 5) and the frame recaptured, up to 25 nudges, then the scan stops with an error. The software shift only corrects the small residual. The take-up spool is wound after every 11 frames, by the angle the legacy `calculateAngleForSpoolTakeUp` computes (`app/takeup.py`). Five frames in a row without a detected hole stops the scan with a "sprocket hole lost" error. Firmware is MicroPython, with the protocol parser and motion profile in pure Python so they are tested on a PC.

**Output per scan.** A folder per reel: `frames/frame_00000001.png`, `scan.json` (settings, frame count, flagged frames).

**Errors**
- Sprocket not found: retry capture a few times, then reuse the previous offset, flag the frame, and continue.
- Controller unresponsive: pause the scan and show the error.

**Testing**
- `align.py` tested against `Sample_Images/`.
- Scan loop tested with a fake controller and fake camera.
- Motion and light verified on the hardware prototype.

**Config.** `config.json` carries over; settings are editable from the web UI.

## Cost estimate (USD, rough, check live prices)

| Item | Estimate |
|---|---|
| Pi 4 (2 GB) | 45 |
| Pi HQ Camera (used or clone; about 75-80 new from third parties) | 55 |
| Pimoroni microscope lens 0.12-1.8x | 30 |
| 2x NEMA 17 pancake steppers | 20 |
| Controller board (Pico + 2x TMC2209 modules, later a PCB) | 20 |
| LED (single COB), driver, diffuser | 15 |
| 12 V 2 A PSU, buck converter, cables, microSD | 25 |
| Printed case and parts, filament, rubber wheel, hardware | 20 |
| **Total** | **~$230** |

If the HQ camera is bought new at about $75-80, the total is about $250-255. A Pi 5 instead of the Pi 4 adds about $35.

## Out of scope for v1

- Built-in touchscreen
- HDR (multi-exposure) capture
- Regular 8 and 16 mm formats
- Upgrading to a sharper fixed-magnification enlarger lens
- CE/FCC certification
- Auto-denoise (kept as an opt-in setting only)

## Open questions

- Whether the microscope lens is sharp enough across the full frame (hands-on test; fallback is an enlarger lens).
- Whether the microscope lens remains available from retailers (some list it as discontinued).
- Pi 4 (2 GB) is the default target; confirm capture and alignment speed on it.
- Whether to do a clean-room rewrite for a different licence if this becomes a commercial product.
