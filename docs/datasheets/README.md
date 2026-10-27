# Datasheet links

Links to the official documents for the parts in the bill of materials (`../design/hardware.md`). Checked 2026-10-27 with `curl -sIL` (HEAD, then a ranged GET where noted), default user agent, from the author's machine.

Status key: **200** = curl returned 200 after redirects. **403 (curl)** = 403 to curl; not otherwise verified (unless a row says it loaded in a fetch tool). **timeout** = curl got no reply in 30 s on HTTP/1.1 and HTTP/2; not verified.

## Parts fixed by the design

| Component | Role | Manufacturer | Links | Document (revision shown) | Checked | Status | Notes |
|---|---|---|---|---|---|---|---|
| Raspberry Pi 4 Model B | Host: camera, app, storage | Raspberry Pi | [datasheet](https://datasheets.raspberrypi.com/rpi4/raspberry-pi-4-datasheet.pdf), [product](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/) | "Raspberry Pi 4 Model B datasheet", ID RP-008341-DS-1 (cover date not read) | 2026-10-27 | datasheet 200; product 403 (curl) | GPIO and CSI limits. |
| Raspberry Pi High Quality Camera (IMX477 board) | Frame capture | Raspberry Pi | [product brief](https://datasheets.raspberrypi.com/hq-camera/hq-camera-product-brief.pdf), [product](https://www.raspberrypi.com/products/raspberry-pi-high-quality-camera/), [Pimoroni](https://shop.pimoroni.com/en-us/products/raspberry-pi-high-quality-camera) | "Raspberry Pi High Quality Camera product brief", ID RP-008202-DS-1 (cover date not read) | 2026-10-27 | brief 200; Pimoroni 200; product 403 (curl, page loads in a fetch tool) | The Sony IMX477 sensor datasheet is NDA-only and is not linked. |
| Raspberry Pi Pico | Motion and LED controller board | Raspberry Pi | [datasheet](https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf), [product](https://www.raspberrypi.com/products/raspberry-pi-pico/) | "Raspberry Pi Pico datasheet", ID RP-008307-DS-2 (cover date not read) | 2026-10-27 | datasheet 200; product 403 (curl) | Pinout and GPIO limits. |
| RP2040 | Microcontroller on the Pico | Raspberry Pi | [datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf) | "RP2040 Datasheet", ID RP-008371-DS-1 (cover date not read) | 2026-10-27 | 200 | PWM slices (LED at 20 kHz, outside the RCD-24's range, see `../design/wiring.md` section 6), PIO. |
| Trinamic TMC2209 | Stepper driver (x2) | Analog Devices (Trinamic) | [datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/tmc2209_datasheet_rev1.09.pdf), [product](https://www.analog.com/en/products/tmc2209.html) | "TMC2209 Datasheet", Rev. 1.09, February 2023 (from the product page listing; PDF not opened) | 2026-10-27 | timeout (not verified; rechecked again for Task 20: curl exit 92 and 28, a fetch tool timed out; a trinamic.com URL redirects to Analog's support page) | URLs come from the Analog Devices search listing. Re-check from another network. Module breakout boards vary; check the seller's pinout too. |
| Pimoroni microscope lens 0.12-1.8x (CAM011) | Optics, C-mount | Pimoroni | [product](https://shop.pimoroni.com/en-us/products/microscope-lens-0-12-1-8x) | No datasheet published; product page only | 2026-10-27 | 200 | Specs are on the product page. |
| Picamera2 manual | Camera API used by `app/` | Raspberry Pi | [manual PDF](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf), [camera software docs](https://www.raspberrypi.com/documentation/computers/camera_software.html) | "The Picamera2 Library", ID RP-008156-DS-6 (cover date not read) | 2026-10-27 | PDF 200; docs page 403 (curl) | The PDF is filed under the Camera Module 2 on Raspberry Pi's site but covers the library in general. |

## Parts chosen in the v3 bill of materials (2026-10-27)

Parts from [`../design/bom.md`](../design/bom.md). Same check method as above (plain `curl -sIL`, no user-agent change, no bot-protection workaround). "Read" means the PDF was downloaded and text extracted; the values taken from it are in `../design/wiring.md` and `../design/bom.md`. Guessed URLs that returned 404 are not listed.

| Component | Role | Manufacturer | Links | Document (revision shown) | Status | Notes |
|---|---|---|---|---|---|---|
| RCD-24-0.70 | LED constant-current driver | RECOM | [datasheet](https://recom-power.com/pdf/Lightline_DC-DC/RCD-24.pdf), [DigiKey](https://www.digikey.ca/en/products/detail/recom-power/RCD-24-0-70/2256303) | "RCD-24 Series", REV 1/2016 | datasheet 200 (read); DigiKey 403 (curl) | PDF link taken from the DigiKey page via a fetch tool. recom-power.com product page: no working URL found (guesses 404). The revision is from 2016: check for a newer one. |
| XLamp CXA1304 | COB LED, 9 V class | Cree LED | [datasheet](https://assets.cree-led.com/a/ds/x/XLamp-CXA1304.pdf), [DigiKey](https://www.digikey.com.br/en/products/detail/cree-led/CXA1304-0000-000C0UA450H/4436426) | "XLamp CXA1304 LED", CLD-DS73 REV 11A | datasheet 200 (read; redirects to downloads.cree-led.com); cree-led.com 200; product page URL not found (guess 404); DigiKey not checked by curl (403 seen on other DigiKey pages) | Order code CXA1304-0000-000C0UA450H. |
| LUMAWISE solderless holder for CXA13 | LED holder | TE Connectivity | [DigiKey range](https://www.digikey.it/en/product-highlight/t/te-connectivity/lumawise-solderless-led-holders) | TE part 2-2154857-2 (from BOM, unconfirmed) | te.com pages and document URL 403 (curl); not read | Datasheet not read: confirm the part number for CXA13 and the footprint. |
| SK 577 50 SA | Heat sink | Fischer Elektronik | [DigiKey](https://www.digikey.co.uk/en/products/detail/fischer-elektronik/SK-577-50-SA/26281512) | none read | fischerelektronik.de 403 (curl); not read | Check mounting and thermal figures on the maker's datasheet. |
| OKX-T/5-D12P-C | 5 V 5 A step-down module for the Pi | Murata Power Solutions | [DigiKey](https://www.digikey.co.uk/product-detail/en/murata-power-solutions-inc/OKX-T-5-D12P-C/811-3190-ND/3313548) | none read | power.murata.com answers with a bot-protection challenge page (Incapsula) to curl, not read; DigiKey 403 not rechecked | No datasheet URL could be confirmed. The 5 V trim resistor value is not taken from any datasheet. |
| TMC2209-SILENTSTEPSTICK | Stepper driver module (x2) | Analog Devices (Trinamic) | [DigiKey](https://digikey.cn/en/products/detail/analog-devices-inc-maxim-integrated/TMC2209SILENTSTEPSTICK/10232488) | none read | analog.com product and PDF URLs: connection failure or timeout on 2026-10-27 (curl exit 92 and 28) | Module user guide not found. The chip datasheet is in the TMC2209 row above. |
| 03455LS1H | Panel fuse holder, 5 x 20 mm | Littelfuse | [DigiKey](https://www.digikey.ca/en/products/detail/littelfuse-inc/03455LS1H/553826) | none read | littelfuse.com 403 (curl); not read | Confirm the holder's current and voltage rating against the fuse chosen. |
| YXJ series (35YXJ100M, 100 uF 35 V) | VM capacitors | Rubycon | [datasheet](https://www.rubycon.co.jp/wp-content/uploads/catalog-aluminum/YXJ.pdf), [DigiKey](https://www.digikey.com.mx/en/products/detail/rubycon/35YXJ100MT16-3X11/3567635) | "YXJ Series" radial lead aluminum electrolytic capacitors (revision not shown) | datasheet 200 (read) | 35 V 100 uF is 6.3 x 11 mm in the table. |

## Parts with no datasheet to link

Not on DigiKey per the BOM. Add the datasheet once a model is chosen.

| Component | Role | Specs to look for | Source named in the BOM |
|---|---|---|---|
| NEMA 17 pancake stepper (x2) | Film and reel drive | Rated current per phase (must suit the TMC2209 current setting), holding torque, step angle, coil resistance and inductance, body length, shaft | STEPPERONLINE pancake, 1 A, 17 Ncm, 23 mm, from Amazon (model code to confirm) |
| Opal diffuser | Even light behind the gate | Material and thickness, transmission, colour cast | Opal acrylic or Perspex Diffuse, 2-3 mm; vendors in the BOM |
| JST XH connectors | Motor and signal connectors | Pitch, current rating, crimp contact part number | JST B4B-XH-A, XHP-4, SXH-001T-P0.6; search DigiKey |
| 12 V supply (Bel/CUI SDI65-12-UC-P5) | Motors and LED | Rated current (5 A), connector polarity, protections | [DigiKey](https://www.digikey.ca/en/products/detail/bel-power-solutions/SDI65-12-UC-P5/5297499); datasheet not read |
| DC barrel panel jack | 12 V inlet | 5.5 x 2.1 mm, rated 5 A or more | Not yet chosen |

## Notes

These documents belong to their publishers. They are not stored in this repository, and links can move. If a link breaks, search for the document name in the "Document" column on the manufacturer's site.
