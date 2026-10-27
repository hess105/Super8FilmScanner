# Datasheet links

Links to the official documents for the parts in the bill of materials (`../design/hardware.md`). Checked 2026-10-27 with `curl -sIL` (HEAD, then a ranged GET where noted), default user agent, from the author's machine.

Status key: **200** = curl returned 200 after redirects. **403 (curl)** = the site's bot protection rejects curl; the page was opened another way and loads, but curl did not return 200. **timeout** = curl got no reply in 30 s on HTTP/1.1 and HTTP/2; not verified.

## Parts fixed by the design

| Component | Role | Manufacturer | Links | Document (revision shown) | Checked | Status | Notes |
|---|---|---|---|---|---|---|---|
| Raspberry Pi 4 Model B | Host: camera, app, storage | Raspberry Pi | [datasheet](https://datasheets.raspberrypi.com/rpi4/raspberry-pi-4-datasheet.pdf), [product](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/) | "Raspberry Pi 4 Model B datasheet", ID RP-008341-DS-1 (cover date not read) | 2026-10-27 | datasheet 200; product 403 (curl) | GPIO and CSI limits. |
| Raspberry Pi High Quality Camera (IMX477 board) | Frame capture | Raspberry Pi | [product brief](https://datasheets.raspberrypi.com/hq-camera/hq-camera-product-brief.pdf), [product](https://www.raspberrypi.com/products/raspberry-pi-high-quality-camera/), [Pimoroni](https://shop.pimoroni.com/en-us/products/raspberry-pi-high-quality-camera) | "Raspberry Pi High Quality Camera product brief", ID RP-008202-DS-1 (cover date not read) | 2026-10-27 | brief 200; Pimoroni 200; product 403 (curl, page loads in a fetch tool) | The Sony IMX477 sensor datasheet is NDA-only and is not linked. |
| Raspberry Pi Pico | Motion and LED controller board | Raspberry Pi | [datasheet](https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf), [product](https://www.raspberrypi.com/products/raspberry-pi-pico/) | "Raspberry Pi Pico datasheet", ID RP-008307-DS-2 (cover date not read) | 2026-10-27 | datasheet 200; product 403 (curl) | Pinout and GPIO limits. |
| RP2040 | Microcontroller on the Pico | Raspberry Pi | [datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf) | "RP2040 Datasheet", ID RP-008371-DS-1 (cover date not read) | 2026-10-27 | 200 | PWM slices (LED at 20 kHz), PIO. |
| Trinamic TMC2209 | Stepper driver (x2) | Analog Devices (Trinamic) | [datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/tmc2209_datasheet_rev1.09.pdf), [product](https://www.analog.com/en/products/tmc2209.html) | "TMC2209 Datasheet", Rev. 1.09, February 2023 (from the product page listing; PDF not opened) | 2026-10-27 | timeout (not verified) | URLs come from the Analog Devices search listing. Re-check from another network. Module breakout boards vary; check the seller's pinout too. |
| Pimoroni microscope lens 0.12-1.8x (CAM011) | Optics, C-mount | Pimoroni | [product](https://shop.pimoroni.com/en-us/products/microscope-lens-0-12-1-8x) | No datasheet published; product page only | 2026-10-27 | 200 | Specs are on the product page. |
| Picamera2 manual | Camera API used by `app/` | Raspberry Pi | [manual PDF](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf), [camera software docs](https://www.raspberrypi.com/documentation/computers/camera_software.html) | "The Picamera2 Library", ID RP-008156-DS-6 (cover date not read) | 2026-10-27 | PDF 200; docs page 403 (curl) | The PDF is filed under the Camera Module 2 on Raspberry Pi's site but covers the library in general. |

## Parts with no model chosen yet

No links yet. Add the datasheet once a model is chosen, and look for these specs.

| Component | Role | Specs to look for | Status |
|---|---|---|---|
| NEMA 17 pancake stepper (x2) | Film and reel drive | Rated current per phase (must suit the TMC2209 current setting), holding torque, step angle, coil resistance and inductance, body length, shaft | Not chosen |
| High-CRI COB LED (95+ CRI) | Backlight | Forward voltage, rated current, CRI (Ra, R9), colour temperature, thermal resistance, heat-sink needs | Not chosen |
| Constant-current PWM LED driver | LED current control | Output current range, input voltage, PWM dimming input range and logic level (Pico GPIO is 3.3 V), PWM frequency limits (firmware uses 20 kHz) | Not chosen |
| 12 V supply | Motors and LED | Rated current (2 A target), ripple, connector, protections | Not chosen |
| 5 V buck converter | Pi power | Output current (Pi 4 needs about 3 A), input range, ripple, efficiency | Not chosen |
| Opal diffuser | Even light behind the gate | Material and thickness, transmission, colour cast | Not chosen |

## Notes

These documents belong to their publishers. They are not stored in this repository, and links can move. If a link breaks, search for the document name in the "Document" column on the manufacturer's site.
