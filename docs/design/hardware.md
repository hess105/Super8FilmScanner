# Hardware

Hardware here is the design intent. The code in `firmware/` is the source of truth for pins; the mechanical and electrical designs themselves are separate pieces of work (see `docs/ROADMAP.md`).

## 1. Bill of materials

Prices are rough USD estimates; check live prices.

| Item | Estimate |
|---|---|
| Raspberry Pi 4 (2 GB) | 45 |
| Pi HQ Camera (used or clone about 55; about 75-80 new from third parties) | 55 |
| Pimoroni microscope lens 0.12-1.8x | 30 |
| 2x NEMA 17 pancake steppers | 20 |
| Controller (Pico + 2x TMC2209 modules, later a PCB) | 20 |
| LED (single COB), driver, diffuser | 15 |
| 12 V 2 A PSU, buck converter, cables, microSD | 25 |
| Printed case and parts, filament, rubber wheel, hardware | 20 |
| **Total** | **about 230** |

If the camera is bought new the total is about $250-255. A Pi 5 instead of the Pi 4 adds about $35. Upgrading to an enlarger lens later adds about $35-135.

## 2. Pin map (`firmware/pins.py`, Pico GPIO numbers)

| Signal | GPIO |
|---|---|
| Film STEP / DIR / EN | 2 / 3 / 4 |
| Reel STEP / DIR / EN | 5 / 6 / 7 |
| Sensor input (reserved, not read by the firmware yet) | 14 |
| LED PWM (20 kHz) | 15 |

EN is active low on the TMC2209. The firmware drives EN high at start (motors off) and low for a move.

## 3. Wiring overview

The Pi talks to the Pico over one USB cable (it appears as `/dev/ttyACM0`). The Pico drives two TMC2209 driver modules and one LED driver channel. A 12 V supply feeds the motor drivers and the LED driver, and a buck converter makes 5 V for the Pi.

| From | To | Notes |
|---|---|---|
| Pi USB | Pico USB | Serial commands and Pico power |
| Pico GPIO 2, 3, 4 | TMC2209 (film) STEP, DIR, EN | Film motor holds position after a move |
| Pico GPIO 5, 6, 7 | TMC2209 (reel) STEP, DIR, EN | Reel motor released after each move |
| Pico GPIO 15 | LED driver PWM input | Constant-current driver with PWM dimming |
| Pico GPIO 14 | Sensor (optional) | Reserved |
| 12 V supply | TMC2209 VM, LED driver | Add a bulk capacitor at the drivers |
| 12 V supply | Buck converter -> 5 V | Powers the Pi |
| Pi CSI | HQ camera | Ribbon cable |
| Motor coils | TMC2209 outputs | Per the module's pinout; check coil pairs before powering |

## 4. Requirements for the separate hardware plans

**Enclosure and film path**
- Projector layout: feed reel, guide rollers, film gate, sprocket and rubber-wheel drive, take-up reel. Supports 3" to 7" reels.
- Flat gate, wide enough to show the sprocket hole and film edges. No moving parts on the image side.
- Camera mount for the C-mount microscope lens, with focus and zoom that can be locked.
- Printed case holding the Pi and electronics. Power inlet, USB storage port and Ethernet on the back.
- Existing FreeCAD parts are updated or replaced; check how they map onto the new layout first.

**Controller PCB**
- RP2040, 2x TMC2209, one LED driver channel, one sensor input, 12 V in with a buck converter to 5 V.
- Two-layer. Prototype on perfboard first, using the pin map above.

**Lighting**
- 95+ CRI white LED, constant-current driver with PWM dimming, opal diffuser behind the gate. Light and exposure stay fixed during a scan.

## 5. Calibration procedure

Edit `scanner.json` (keys as in `app/config.py`) and restart the app after each change.

1. Light and detection: load a reel with the gate lit. Move the light slider; the light should follow. Press "Test frame". If the hole is not found, adjust `sprocket_threshold` (default 230) or `sprocket_strip_frac` (default 0.16).
2. `exposure_us` and `gain`: set so the picture is bright but the sprocket hole is the brightest area and the film is not clipped. Use gain 1.0 where possible. White balance is locked at start with the empty gate lit.
3. `flip_vertical`: if the film nudges the wrong way (the hole moves away from the target), set it the other way.
4. `steps_per_frame` (default 164) and `nudge_*`: scan about 20 frames and watch for nudges. Adjust `steps_per_frame` until nudges are rare. Tune `nudge_forward_steps`, `nudge_reverse_steps` and `nudge_rate` if corrections overshoot or are slow.
5. `reel_steps_per_rev` (default 3200): set to the motor's steps per revolution including microstepping and any gearing. Check that the take-up spool keeps the film taut but not pulled over a full reel.
6. Check run: scan about 50 frames. Frames must be full size, the hole in the same position in every frame, nothing cropped, `reel.mp4` playing at 18 fps, and grain intact (denoise is off by default).
