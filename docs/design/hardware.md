# Hardware

Hardware here is the design intent. The code in `firmware/` is the source of truth for pins; the mechanical and electrical designs themselves are separate pieces of work (see `docs/ROADMAP.md`).

## 1. Bill of materials

The v3 selection is in [bom.md](bom.md), with links, ordering codes and the checks to make before ordering. All prices are rough USD **estimates**; DigiKey part numbers and prices come from search listings (DigiKey blocks automated fetches), so check live stock and price. Datasheets: [index](../datasheets/README.md).

| Item | Selection | Low-high estimate |
|---|---|---|
| Computer | Raspberry Pi 4 Model B, 2 GB (2 GB price not retrieved; estimate) | 45-60 |
| Camera | Pi HQ Camera (not on DigiKey; PiShop or other resellers) | 55 |
| Lens | Pimoroni microscope lens 0.12-1.8x | 30 |
| Motors | 2x NEMA 17 pancake steppers (owner's pick, Amazon) | 20 |
| Controller | Pico (SC0915) 5, 2x official TMC2209-SILENTSTEPSTICK 38 | 43 |
| LED | Cree CXA1304 8-15, RECOM RCD-24-0.70 13-21, TE LUMAWISE holder 2-5, Fischer SK 577 50 SA heat sink 15-20 (opal diffuser not priced) | 38-61 |
| 12 V and 5 V | Bel/CUI SDI65-12-UC-P5 12 V 5 A adapter 43, Murata OKX-T/5-D12P-C 5 V module 8 | 51 |
| Protection and parts | Littelfuse 03455LS1H fuse holder and fuse, Rubycon capacitors, JST XH connectors, barrel jack, wire, perfboard, microSD | 25 |
| Printed case and parts, filament, rubber wheel, hardware | Retail | 20 |
| **Total** | Sum of the rows: low 45+55+30+20+43+38+51+25+20 = 327; high 60+55+30+20+43+61+51+25+20 = 365 | **about 330-365 without the SSD** |

An SSD for frames (1 TB) adds about $70-90. A **budget swap** replaces the official TMC2209 modules (38) with third-party modules (about 16, per the BOM), the 12 V adapter (43) with a generic 12 V 5 A adapter (about 22, per the BOM) and the Murata module (8) with a Pololu D24V50F5 5 V regulator (price not retrieved; I assume 15-20, an estimate): low 327 - 89 + 16 + 22 + 15 = 291, high 365 - 89 + 16 + 22 + 20 = 334, so about **$290-335 without the SSD**. All prices are estimates. A Pi 5 instead of the Pi 4 adds about $35. Upgrading to an enlarger lens later adds about $35-135.

**Lead-time risks** (as shown on DigiKey pages, not confirmed): Murata 5 V module 38 weeks, official TMC2209 module 16-19 weeks, RECOM driver 10-17 weeks, 12 V adapters 12-28 weeks depending on model. The LED section also has a design issue to resolve before relying on the parts: the RCD-24's PWM input is active low and rated to 1 kHz, while the firmware drives 20 kHz ([wiring](wiring.md) section 6, [roadmap](../ROADMAP.md)).

## 2. Pin map (`firmware/pins.py`, Pico GPIO numbers)

| Signal | GPIO |
|---|---|
| Film STEP / DIR / EN | 2 / 3 / 4 |
| Reel STEP / DIR / EN | 5 / 6 / 7 |
| Sensor input (reserved, not read by the firmware yet) | 14 |
| LED PWM (20 kHz; outside the RCD-24's range, see wiring.md section 6) | 15 |

EN is active low on the TMC2209. The firmware drives EN high at start (motors off) and low for a move. Each EN line needs an external pull-up to VIO: the RP2040 pulls its GPIOs down at reset, so without it the drivers are enabled until the firmware runs (see `wiring.md`).

## 3. Wiring overview

The Pi talks to the Pico over one USB cable (it appears as `/dev/ttyACM0`). The Pico drives two TMC2209 driver modules and one LED driver channel. A 12 V supply feeds the motor drivers and the LED driver, and a Murata 5 V module makes 5 V for the Pi.

Full schematics, pin table and bring-up checks: [wiring](wiring.md).

| From | To | Notes |
|---|---|---|
| Pi USB | Pico USB | Serial commands and Pico power |
| Pico GPIO 2, 3, 4 | TMC2209 (film) STEP, DIR, EN | Film motor holds position after a move |
| Pico GPIO 5, 6, 7 | TMC2209 (reel) STEP, DIR, EN | Reel motor released after each move |
| Pico GPIO 15 | RCD-24-0.70 PWM/ON/OFF input (pin 3) | Active low, rated to 1 kHz; see wiring section 6 |
| Pico GPIO 14 | Sensor (optional) | Reserved |
| 12 V supply | TMC2209 VM, LED driver | Add a bulk capacitor at the drivers |
| 12 V supply | Murata OKX-T/5-D12P-C -> 5 V | Powers the Pi |
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
- RP2040, 2x TMC2209, one LED driver channel, one sensor input, 12 V in with a 5 V module for the Pi.
- Two-layer. Prototype on perfboard first, using the pin map above.

**Lighting**
- CXA1304 COB LED (5000 K, CRI 90 minimum), RECOM RCD-24-0.70 constant-current driver, opal diffuser behind the gate. Light and exposure stay fixed during a scan.

## 5. Calibration procedure

Edit `scanner.json` (keys as in `app/config.py`) and restart the app after each change.

1. Light and detection: load a reel with the gate lit. Move the light slider; the light should follow (with the RCD-24 driver the slider direction may be inverted and out of range until the firmware item in `docs/ROADMAP.md` lands; see `wiring.md` section 6). Press "Test frame". If the hole is not found, adjust `sprocket_threshold` (default 230) or `sprocket_strip_frac` (default 0.16).
2. `exposure_us` and `gain`: set so the picture is bright but the sprocket hole is the brightest area and the film is not clipped. Use gain 1.0 where possible. White balance is locked at start with the empty gate lit.
3. `flip_vertical`: if the film nudges the wrong way (the hole moves away from the target), set it the other way.
4. `steps_per_frame` (default 164) and `nudge_*`: scan about 20 frames and watch for nudges. Adjust `steps_per_frame` until nudges are rare. Tune `nudge_forward_steps`, `nudge_reverse_steps` and `nudge_rate` if corrections overshoot or are slow.
5. `reel_steps_per_rev` (default 3200): set to the motor's steps per revolution including microstepping and any gearing. Check that the take-up spool keeps the film taut but not pulled over a full reel.
6. Check run: scan about 50 frames. Frames must be full size, the hole in the same position in every frame, nothing cropped, and grain intact (encode a test MP4 on a computer to check 18 fps playback) (denoise is off by default).
