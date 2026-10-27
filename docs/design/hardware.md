# Hardware

Hardware here is the design intent. The code in `firmware/` is the source of truth for pins; the mechanical and electrical designs themselves are separate pieces of work (see `docs/ROADMAP.md`).

## 1. Bill of materials

The v4 lean selection is in [bom.md](bom.md), with sources, availability evidence, ordering codes and the checks to make before ordering. All prices are rough USD **estimates**; DigiKey part numbers and prices come from search listings (DigiKey blocks automated fetches), so check live stock and price. Datasheets: [index](../datasheets/README.md).

| Item | Selection | Low-high estimate |
|---|---|---|
| Computer | Raspberry Pi 4 Model B, 2 GB (Pi reseller; 2 GB DigiKey price not retrieved) | 45-60 |
| Camera | Pi HQ Camera (PiShop or other resellers) | 55 |
| Lens | Pimoroni microscope lens 0.12-1.8x | 30 |
| Motors | 2x NEMA 17 pancake steppers (owner's pick, Amazon) | 20 |
| Controller | Pico (DigiKey SC0915) | 5 |
| Drivers | 2x Adafruit TMC2209 breakout (product 6121, $8.95 each on Adafruit) | 18 |
| LED group | Cree CXA1304 about 20 (DigiKey), Mean Well LDD-350L 5-10 (DigiKey), T-Global TGH-0400-03 heat sink 6-10 (DigiKey); no holder, opal diffuser not priced | 31-40 |
| Power | Generic UL-listed 24 V 2 A adapter 12-15 (not DigiKey), Pi USB-C supply 8-12 (reseller) | 20-27 |
| Protection and parts | Littelfuse 03455LS1H fuse holder and fuse, Rubycon capacitors, JST XH connectors, barrel jack, wire, perfboard, microSD | 15 |
| Printed case and parts, filament, rubber wheel, hardware | Retail | 20 |
| **Total** | Sum of the rows: low 45+55+30+20+5+18+31+20+15+20 = 259; high 60+55+30+20+5+18+40+27+15+20 = 290 | **about 259-290 without storage** |

Storage: a 50 ft reel is about 58-90 GB of PNGs. Use an existing USB drive or network share, or a 256 GB drive (about $25), or a 1 TB SSD (about $70-90); storage is not in the total. With a DigiKey 24 V adapter (Bel SDI50-24-UC-P5, estimated 25-35) instead of the generic one the total is about 272-310. All prices are estimates. A Pi 5 instead of the Pi 4 adds about $35. Upgrading to an enlarger lens later adds about $35-135.

**Lead-time risks** (as shown on listings, not confirmed): Mean Well LDD-350L 12 weeks on one DigiKey page, T-Global TGH-0400-03 15 weeks in the listing text (contradictory with its stock figure). Each DigiKey part is an availability check on the day (`ROADMAP.md`).

## 2. Pin map (`firmware/pins.py`, Pico GPIO numbers)

| Signal | GPIO |
|---|---|
| Film STEP / DIR / EN | 2 / 3 / 4 |
| Reel STEP / DIR / EN | 5 / 6 / 7 |
| Sensor input (reserved, not read by the firmware yet) | 14 |
| LED PWM (unused and reserved; leave unconnected, see wiring.md section 6) | 15 |

EN is active low on the TMC2209. The firmware drives EN high at start (motors off) and low for a move. Each EN line needs an external pull-up to VIO: the RP2040 pulls its GPIOs down at reset, so without it the drivers are enabled until the firmware runs (see `wiring.md`).

## 3. Wiring overview

The Pi talks to the Pico over one USB cable (it appears as `/dev/ttyACM0`). The Pico drives two TMC2209 driver modules. One 24 V adapter feeds the motor drivers and the LED driver (through a fuse); the Pi runs from its own USB-C 5.1 V 3 A supply, so there is no 5 V step-down module. The LED is fixed brightness: its driver's dimming pin and Pico GPIO 15 are not connected.

Full schematics, pin table, star ground and bring-up checks: [wiring](wiring.md).

| From | To | Notes |
|---|---|---|
| Pi USB | Pico USB | Serial commands and Pico power |
| Pico GPIO 2, 3, 4 | TMC2209 (film) STEP, DIR, EN | Film motor holds position after a move |
| Pico GPIO 5, 6, 7 | TMC2209 (reel) STEP, DIR, EN | Reel motor released after each move |
| Pico GPIO 15 | Nothing (unused, reserved) | The LDD-350L dimming pin (pin 3) stays open |
| Pico GPIO 14 | Sensor (optional) | Reserved |
| 24 V adapter, through the fuse | TMC2209 VM (x2), LDD-350L +Vin (pin 1) | 100 uF capacitor at each driver; one star ground |
| Pi USB-C supply | Pi | Own supply |
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
- RP2040, 2x TMC2209 breakouts, a fixed-current LED driver, one sensor input, one 24 V input; the Pi has its own USB-C supply (no 5 V module).
- Two-layer. Prototype on perfboard first, using the pin map above.

**Lighting**
- CXA1304 COB LED (9 V class, 90 CRI minimum, 5000 K per the order code) on a Mean Well LDD-350L constant-current driver from the 24 V rail, with the driver's dimming pin left open (fixed full 350 mA) and a TGH-0400-03 pin-fin heat sink, opal diffuser behind the gate. Light and exposure stay fixed during a scan. Heat sink margin is a bring-up measurement ([wiring](wiring.md) section 6).

## 5. Calibration procedure

Edit `scanner.json` (keys as in `app/config.py`) and restart the app after each change.

1. Light and detection: load a reel with the gate lit. The LED is fixed brightness (the LDD-350L dimming pin is open and GPIO 15 is unused), so there is no light slider to move: when `light_control` is false in `scanner.json` the web page hides the light slider (false is the default). Set the picture brightness with `exposure_us` and `gain` (step 2). Before the first long run, do the LED temperature check in `wiring.md` section 6 (case temperature after 30 minutes). Press "Test frame". If the hole is not found, adjust `sprocket_threshold` (default 230) or `sprocket_strip_frac` (default 0.16).
2. `exposure_us` and `gain`: set so the picture is bright but the sprocket hole is the brightest area and the film is not clipped. Use gain 1.0 where possible. White balance is locked at start with the empty gate lit.
3. `flip_vertical`: if the film nudges the wrong way (the hole moves away from the target), set it the other way.
4. `steps_per_frame` (default 164) and `nudge_*`: scan about 20 frames and watch for nudges. Adjust `steps_per_frame` until nudges are rare. Tune `nudge_forward_steps`, `nudge_reverse_steps` and `nudge_rate` if corrections overshoot or are slow.
5. `reel_steps_per_rev` (default 3200): set to the motor's steps per revolution including microstepping and any gearing. Check that the take-up spool keeps the film taut but not pulled over a full reel.
6. Check run: scan about 50 frames. Frames must be full size, the hole in the same position in every frame, nothing cropped, and grain intact (encode a test MP4 on a computer to check 18 fps playback) (denoise is off by default).
