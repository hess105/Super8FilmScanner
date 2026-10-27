# Bill of materials v4: lean parts, DigiKey only where DigiKey has stock

Status: adopted by `hardware.md`, `wiring.md`, the datasheet index and the roadmap (Task 21). Prices are estimates in USD. This replaces v3 (about $327-365).

**How this was sourced, and what it is worth.** DigiKey's pages block automated fetches (HTTP 403, a Cloudflare challenge), so every DigiKey part number, price, stock figure and lead time below comes from web-search listings of DigiKey regional pages (and a few aggregators), seen on 2026-10-27, not from a page opened and read. Stock and lead time differ by regional site and change daily: **search listing, check the page on the day** applies to every DigiKey row. A DigiKey part is kept only where a listing showed stock or a reasonable lead time; otherwise the part is sourced elsewhere (see the "not DigiKey" rows). Datasheet values quoted here were read from the official PDF where a page is cited; everything else is marked **VERIFY**.

**What the lean build is.** A fixed-brightness LED (Cree CXA1304 on a Mean Well LDD-350L constant-current driver, dimming pin left open, small pin-fin heat sink, no holder), Adafruit TMC2209 breakouts, **one 24 V supply** for the motors and the LED, and the Pi on its own USB-C supply (so no 5 V step-down module). Why 24 V and not 12 V: the Mean Well LDD-L steps its output down by at least 3 V from its input (LDD-L-SPEC dated 2026-09-15, page 1 note 4), and the 9 V-class CXA1304 needs about 9.0-9.9 V (Cree CLD-DS73 REV 11A page 17, graph read approximately), so 12 V cannot drive it ([wiring](wiring.md) section 6).

## Parts

| Part | Selection | Source | Availability evidence (search listing, check the page on the day) | Est. USD | Check before ordering |
|---|---|---|---|---|---|
| Controller | Raspberry Pi **Pico** (RP2040) | DigiKey [SC0915](https://www.digikey.de/en/products/detail/raspberry-pi/SC0915/13684020) | US listing about $4.59 cut tape, about 50,899 in stock | 5 | none |
| LED (COB) | Cree XLamp **CXA1304-0000-000C0UA450H**, 13.35 mm square, 9 V class, 90 CRI minimum, 5000 K per the code | DigiKey, **no page of its own found**; DigiKey code CXA1304-0000-000C0UA450H-ND | A substitutes table on the page of the sibling [CXA1304-0000-000C0UA450F](https://www.digikey.hk/en/products/detail/cree-led/CXA1304-0000-000C0UA450F/4436425) (HK) shows the H code with 74 available at $19.90 (crawl snapshot). Siblings show a 4-week manufacturer lead time. Siblings with their own pages: [CXA1304-0000-000C0HB450H](https://www.digikey.com/en/products/detail/cree-led/CXA1304-0000-000C0HB450H/4337113) (80 CRI minimum). An earlier listing, [CXA1304-0000-000C0UA450H on digikey.com.br](https://www.digikey.com.br/en/products/detail/cree-led/CXA1304-0000-000C0UA450H/4436426), was used in v3 | about 20 | Search DigiKey for the exact code and confirm stock; if only the siblings are listed, confirm the CRI (U = 90 minimum, H = 80 minimum), the 9 V class (code C0) and the CCT in the Cree order-code tables (datasheet page 27) before accepting a substitute. **Do not order** CXA1304-0000-000F0HB40E3 ("F0" is the 18 V class). Datasheet facts: [wiring](wiring.md) section 6 |
| LED driver | Mean Well **LDD-350L** (350 mA step-down constant-current, 9-36 V in, 2-32 V out, pin style) | DigiKey 1866-3109-ND, [LDD-350L](https://www.digikey.my/en/products/detail/mean-well-usa-inc/LDD-350L/7704754) | The CN page shows a 12-week manufacturer lead time (not stocked everywhere); an aggregator (myMectronic) showed 817 units dated 2026-06-16 (stale); Master Electronics showed 185 in stock; RS in stock in several regions. Listed prices are inconsistent between sites, so I give a range | 5-10 | Stock and lead time on the page. Substitutes: [LDD-350LS](https://www.digikey.com.br/en/products/detail/mean-well-usa-inc/LDD-350LS/7704759) (SMD style, 2-28 V out; different pins, a different layout: not a drop-in) or LDD-350LW (wired, same pin numbers, wire colours in [wiring](wiring.md) section 6). Alternative if you want more light: **LDD-700L** (700 mA, DigiKey 1866-3121-ND, [page](https://www.digikey.fi/en/products/detail/mean-well-usa-inc/LDD-700L/7704757); listings disagreed: AU out of stock/backorder, HK 1,057 units with a 12-week lead, an aggregator 41 units) with the thermal cost described in [wiring](wiring.md) section 6; the LDD-700LW and LDD-700LS are its variants. Datasheet (read): [LDD-L-SPEC](https://www.meanwell.com/Upload/PDF/LDD-L/LDD-L-SPEC.PDF) |
| Heat sink | T-Global **TGH-0400-03**, square pin-fin, 40 x 40 mm, 11 mm fins | DigiKey [TGH-0400-03](https://www.digikey.ph/en/products/detail/t-global-technology/TGH-0400-03/13682159) | The snippet showed 629 in stock **and** a 15-week lead time text: contradictory, so check the page. Alternative: [TGH-0300-03](https://www.digikey.nl/en/products/detail/t-global-technology/TGH-0300-03/13682147), 30 x 30 x 12 mm (stock not seen). Cooling Source CS9463010BP 30 x 30 x 10 showed 0 in stock | 6-10 (not retrieved, estimate) | **Thermal resistance not read** (t-global.com blocks automated fetches, DigiKey 403). The heat-sink margin is a bring-up measurement, see [wiring](wiring.md) section 6. Confirm the mounting method (holes or adhesive pad) and the thermal interface material |
| Fuse holder | Littelfuse **03455LS1H** 5 x 20 mm panel-mount holder (quick-connect, 10 A, 250 V per the v3 listing) | DigiKey [03455LS1H](https://www.digikey.ca/en/products/detail/littelfuse-inc/03455LS1H/553826) | About 3,693 in stock on the CA listing | 3 | Fit a 5 x 20 mm slow-blow fuse of about 2.5-3.15 A for the 2 A adapter (**VERIFY**; fuse not searched) |
| Capacitors (x2, one spare) | Rubycon **35YXJ100MT16.3X11**, 100 uF 35 V radial, 105 C | DigiKey [3567635](https://www.digikey.com.mx/en/products/detail/rubycon/35YXJ100MT16-3X11/3567635) | About 24,336 in stock, about $0.27 each | 1 | 35 V on a 24 V rail is a modest margin; a **50 V** 100 uF part is the more conservative choice (stock not searched). The Adafruit board already carries a 22 uF 35 V capacitor on motor power |
| Computer | Raspberry Pi 4 Model B, **2 GB** | **Pi reseller** (PiShop and similar) unless DigiKey shows stock: DigiKey lists SC0193(11) as the 2 GB and [SC0194(9)](https://www.digikey.at/en/products/detail/raspberry-pi/SC0194-9/10258781) as the 4 GB | 4 GB showed $75 on a US-facing page; the 2 GB price and stock were not retrieved | 45-60 (estimate) | Compare DigiKey SC0193(11) with a reseller on the day |
| Camera | Raspberry Pi **HQ Camera** (IMX477) | [PiShop](https://www.pishop.us/product/raspberry-pi-hq-camera/) or another Pi reseller (not DigiKey) | No DigiKey listing found; RS says it will stop stocking it | 55 | Lens not included; C-mount, CS adapter in the box |
| Lens | Pimoroni microscope lens 0.12-1.8x | Pimoroni or SparkFun | Not DigiKey | 30 | May be discontinued (roadmap open questions) |
| Motors (x2) | NEMA 17 pancake, 1 A, 17 Ncm, 23 mm (owner's pick) | STEPPERONLINE via Amazon | Not DigiKey | 20 | Model code to be confirmed |
| Stepper drivers (x2) | **Adafruit TMC2209 breakout**, Adafruit product 6121, screw terminals, onboard current potentiometer | [Adafruit 6121](https://www.adafruit.com/product/6121) ($8.95 each for 1-9, "In stock" on Adafruit's page, read 2026-10-27). DigiKey is a listed reseller on that page | DigiKey's price and stock were not retrieved: check DigiKey; if it has none, buy from Adafruit | 17.90 for two (Adafruit price) | Adafruit page facts (not the chip datasheet): motor voltage 5-29 V, logic 3-5 V, up to 2 A, default 1/8 microstep, **MS1 and MS2 both high = 1/16** (needed for 3200 steps per rev), 22 uF 35 V capacitor on board. TMC2209 chip-level items remain **VERIFY**. Alternatives: the official [TMC2209-SILENTSTEPSTICK](https://digikey.cn/en/products/detail/analog-devices-inc-maxim-integrated/TMC2209SILENTSTEPSTICK/10232488) (DigiKey 505-TMC2209SILENTSTEPSTICK-ND, about $19 each, 16-19 weeks lead) or third-party StepStick-format modules (about $8 each, not DigiKey, different pinout: [wiring](wiring.md) section 4 does not apply to them) |
| 24 V supply | Generic **UL- or ETL-listed 24 V 2 A** desktop adapter, 5.5 x 2.1 mm barrel, **centre-positive** | Electronics retailer or marketplace (not DigiKey) | DigiKey options were rejected for the lean default on price/stock (below) | 12-15 (estimate) | Confirm polarity and the listing mark; fit the fuse (see the fuse row). **DigiKey alternatives:** Bel/CUI [SDI50-24-UC-P5](https://www.digikey.ca/en/products/detail/bel-power-solutions/SDI50-24-UC-P5/5297458) (24 V, 50 W, 2.1 A, 2.1 x 5.5 mm barrel, cord included; 1,072 listed on the CA page, 534 on the BR page; price not retrieved, estimate about 25-35), and Tri-Mag [L6R48D-240-C14](https://www.digikey.com.br/en/products/detail/tri-mag-llc/L6R48D-240-C14/8038533) (24 V 48 W 2 A, 2.1 x 5.5 mm barrel; the cord is **sold separately**, with an IEC C14 inlet so a C13 cord is needed; 126 listed on the BR page; price not retrieved) |
| Pi power | Raspberry Pi **USB-C 5.1 V 3 A (15 W)** supply | A Pi reseller (about $8-12) | DigiKey lists SC0216 (UK plug, 464 in stock on the CA page) and SC1412 (EU plug, 3,242 on the IN page), but the US black **SC0218 is "not kept in stock"** (lead time), so a US buyer uses a reseller | 8-12 | Use the official supply or one rated 5.1 V 3 A |
| Diffuser | Opal (milky white) acrylic or light-diffusing sheet, 2-3 mm, cut to about 20 x 20 mm | [Simply Plastics opal sheet](https://www.simplyplastics.com/catalog/products-by-use/plastic-lighting-materials/led-light-diffusing-opal-acrylic-sheet/c-24/c-110/p-676) (UK), [Perspex Diffuse](https://www.display.3acomposites.com/perspex/perspex-light/diffuse/) (60-70 percent transmission) | Not DigiKey | not priced | Pairs with the LED at about 5000 K |
| Connectors, wire, parts | JST XH (B4B-XH-A header, XHP-4 housing, SXH-001T-P0.6 contact; no DigiKey page found for these exact parts), a 5.5 x 2.1 mm panel barrel jack, **lighter wire** (about 22-20 AWG is typical for 2 A, pick from a wire table), two 10 k pull-up resistors, perfboard, headers, microSD | Any distributor | Generic | 15 (with the fuse holder, fuse and capacitors) | Resistor value is **VERIFY** per `wiring.md` |
| Printed case and parts, bearings, O-ring, screws, rubber wheel | Mechanical | Retail | Not DigiKey | 20 | |
| Storage | See the storage note | | | not in the total | |

## Dropped from v3

| Part | Why dropped |
|---|---|
| Murata OKX-T/5-D12P-C 5 V module | 38-week lead time shown, and its 13.8 V input limit does not suit a 24 V rail; the Pi now has its own USB-C supply |
| RECOM RCD-24-0.70 driver | Replaced by the fixed-current Mean Well LDD-350L; the RCD-24 PWM problem (active-low pin, 200 Hz linear / 1 kHz maximum against the firmware's 20 kHz) does not arise because there is no dimming connection |
| TE LUMAWISE LED holder | Solder wires to the COB pads (or clamp it); one less part and its part number was never confirmed |
| Fischer SK 577 50 SA 50 mm heat sink | Oversized for a roughly 3 W LED at 350 mA |
| Bel/CUI SDI65-12-UC-P5 60 W 12 V 5 A adapter | A 12 V rail cannot drive the LED through the LDD-L (3 V step-down), and 60 W is far more than needed; the motor/LED rail is now 24 V 2 A |
| Official TMC2209-SILENTSTEPSTICK as the default | About $19 each with a 16-19 week lead time; kept as an alternative |

## Storage

A 50 ft reel is about 58-90 GB of PNGs. Use an existing USB drive or network share, or buy a 256 GB drive (about $25), or a 1 TB SSD (about $70-90). Storage is not in the totals below.

## Cost

Itemised from the rows above (low-high, USD):

| Item | Low | High |
|---|---|---|
| Pi 4 2 GB | 45 | 60 |
| HQ camera | 55 | 55 |
| Lens | 30 | 30 |
| Motors | 20 | 20 |
| Pico | 5 | 5 |
| 2 x Adafruit TMC2209 (2 x 8.95 = 17.90, rounded to 18) | 18 | 18 |
| LED group: CXA1304 about 20 + LDD-350L 5-10 + TGH-0400-03 6-10 | 31 | 40 |
| Power: 24 V adapter 12-15 + Pi USB-C supply 8-12 | 20 | 27 |
| Wiring, fuse, capacitors, connectors | 15 | 15 |
| Printed parts | 20 | 20 |

Low: 45 + 55 + 30 + 20 + 5 + 18 + 31 + 20 + 15 + 20 = **259**. High: 60 + 55 + 30 + 20 + 5 + 18 + 40 + 27 + 15 + 20 = **290**.

**About $259-290 without storage** (DigiKey and non-DigiKey line items together; with a DigiKey 24 V adapter, SDI50-24-UC-P5 at an estimated 25-35 in place of the generic 12-15, the total rises by 13-20 to about 272-310; storage extra). The LDD-350L price is uncertain: listings range from about $2.65 to $39 across regional pages and aggregators, so the 5-10 is a working estimate, not a quote. Official TMC2209 modules instead of Adafruit's would add about 20 (2 x 19 = 38 against 18).

## Lead-time risks

LDD-350L 12 weeks (CN page), TGH-0400-03 15 weeks (listing text, contradictory with its stock figure), CXA1304 about 4 weeks (siblings), official TMC2209 module 16-19 weeks (alternative only), DigiKey 24 V adapters not tied to a lead time in the listings. Buy the 24 V adapter, Pi supply, Pi, camera, lens and motors from retail sources where stock is immediate.

## Sources

[Raspberry Pi Pico SC0915](https://www.digikey.de/en/products/detail/raspberry-pi/SC0915/13684020), [Cree CXA1304 datasheet](https://assets.cree-led.com/a/ds/x/XLamp-CXA1304.pdf), [CXA1304-0000-000C0UA450F](https://www.digikey.hk/en/products/detail/cree-led/CXA1304-0000-000C0UA450F/4436425), [Mean Well LDD-350L](https://www.digikey.my/en/products/detail/mean-well-usa-inc/LDD-350L/7704754), [Mean Well LDD-L-SPEC](https://www.meanwell.com/Upload/PDF/LDD-L/LDD-L-SPEC.PDF), [T-Global TGH-0400-03](https://www.digikey.ph/en/products/detail/t-global-technology/TGH-0400-03/13682159), [Littelfuse 03455LS1H](https://www.digikey.ca/en/products/detail/littelfuse-inc/03455LS1H/553826), [Rubycon 35YXJ100MT16.3X11](https://www.digikey.com.mx/en/products/detail/rubycon/35YXJ100MT16-3X11/3567635), [Adafruit TMC2209 breakout](https://www.adafruit.com/product/6121) and its [guide](https://learn.adafruit.com/adafruit-tmc2209-stepper-motor-driver-breakout-board), [SDI50-24-UC-P5](https://www.digikey.ca/en/products/detail/bel-power-solutions/SDI50-24-UC-P5/5297458), [L6R48D-240-C14](https://www.digikey.com.br/en/products/detail/tri-mag-llc/L6R48D-240-C14/8038533), [PiShop HQ camera](https://www.pishop.us/product/raspberry-pi-hq-camera/).
