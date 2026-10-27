# Roadmap and next steps

## 1. Status

Built and tested on a PC (fake controller and fake camera, no hardware):
- Firmware protocol parser and motion profile (`firmware/protocol.py`, `firmware/motion.py`).
- App modules: settings, controller wrapper, sprocket detection and alignment, post-processing, spool take-up maths, scan loop, scan runner, web server and page.

Not run on hardware yet:
- The Pico main loop (`firmware/main.py`): flashing and serial check.
- The picamera2 wrapper (`app/camera.py`): real capture.
- The whole machine end to end, and the web page in a browser.

## 2. Timeline

| Phase | Weeks | Goal | Done when |
|---|---|---|---|
| 0. Software and firmware | done | App and firmware written and tested on a PC | tests pass on the branch |
| 1. Bench bring-up | 1-2 | Order parts (about $330-365 without the SSD; [bill of materials](design/bom.md)). Flash the Pico on perfboard with 2 TMC2209 modules, drive both motors and the LED. Set up Pi OS, run the camera check, start the web app. Wiring: [wiring](design/wiring.md) | web UI shows a live preview, light slider works (after the RCD-24 PWM firmware item), "Test frame" finds the sprocket on a loose piece of film |
| 2. Mechanics | 2-5 | Update the FreeCAD parts for the new film path, gate, camera mount and reel mounts; print and iterate | film advances one frame cleanly through the gate without scratching |
| 3. Image quality | 4-6 | Lens focus and zoom, diffuser and LED, exposure, white balance; try an enlarger lens if the microscope lens is soft | frames are sharp across the whole picture and evenly lit |
| 4. First full reel | 6-7 | Calibrate `steps_per_frame` and spool winding; scan a 3-minute reel | 3,000+ aligned frames and a playable MP4 with few or no flagged frames |
| 5. Controller PCB | 7-10 | KiCad design, order from a PCB fab, assemble, flash, replace the perfboard | one scan completes on the PCB |
| 6. Enclosure and release | 10-12 | Finish the printed case, write build and user docs, publish the build files | someone else can build and run it from the docs |

These durations are estimates for one person working about 8-10 hours a week, and they shift with parts delivery.

## 3. To bring up what exists

- [ ] Order the parts (see `docs/design/hardware.md` and [bill of materials](design/bom.md), about $330-365 without the SSD, or about $290-335 with the budget swap; SSD extra). Confirm first on DigiKey:
  - [ ] LED ordering code: CXA1304-0000-000C0UA450H (9 V class, CRI 90 minimum), not the 18 V code CXA1304-0000-000F0HB40E3.
  - [ ] The 2 GB Pi 4 part number and price (SC0193(11) per the BOM).
  - [ ] Murata OKX-T/5-D12P-C trim resistor value and the 38-week lead time (or take the Pololu D24V50F5 alternative).
  - [ ] RECOM RCD-24-0.70: dimming range (see the firmware item below), lead time and whether a newer datasheet than REV 1/2016 exists.
  - [ ] TE LUMAWISE part number for CXA13, and the heat sink mounting.
  - [ ] Fuse rating (BOM suggests 6.3 A, 5 x 20 mm) and lead times of the official TMC2209 modules and the 12 V adapter.
- [ ] Set up Pi OS Bookworm and install per the README.
- [ ] Flash the Pico: `pip install mpremote`, then `mpremote cp firmware/protocol.py firmware/motion.py firmware/pins.py :`, `mpremote cp firmware/main.py :main.py`, `mpremote reset`.
- [ ] Check serial replies (`STATUS`, `LIGHT 30`, `STATUS`, `ADVANCE 164`, `WIND 100`, `FOO`). Expected: `OK light=0`, `OK`, `OK light=30`, `OK`, `OK`, `ERR unknown command`. The LED dims with `LIGHT` only after the RCD-24 PWM firmware item below is done: with the current firmware and the RCD-24, `LIGHT 0` is full on (`docs/design/wiring.md` section 9 step 5).
- [ ] Check the camera captures a full-resolution frame.
- [ ] Run `python -m app --config scanner.json`.
- [ ] First "Test frame": the sprocket hole is found.
- [ ] Calibrate (procedure in `docs/design/hardware.md`).
- [ ] Short 50-frame scan; check frames and alignment.
- [ ] Full reel.

## 4. Known issues and follow-ups

Deferred review findings, none blocking. Each is a checkbox: file, one-line fix.

### Firmware (check on the real Pico)
- [ ] `firmware/main.py`: LED PWM is 20 kHz and active high, but the RECOM RCD-24-0.70 PWM/ON/OFF pin is active low and rated 200 Hz (linear) to 1000 Hz (limit) per its datasheet REV 1/2016 (see `docs/design/wiring.md` section 6). Decide: lower frequency with inverted duty, an RC-filtered PWM into the analogue dimming pin, or a fixed current. Separate task; update wiring.md and `tests` with the change. Confirm on the bench first.
- [ ] `firmware/main.py`: no wait after EN goes low before the first step; add `time.sleep_ms(2)`.
- [ ] `firmware/main.py`: per-step interpreter overhead limits the top step rate; measure, and move to PIO if needed.
- [ ] `firmware/main.py`: exceptions other than `ProtocolError` end the loop; catch and reply `ERR`.
- [ ] `firmware/protocol.py`: step count is unbounded in `parse_command`; cap it if the motor loop needs it.
- [ ] `firmware/protocol.py` tests: add WIND-with-rate and LIGHT 0/100 boundary cases.
- [ ] `firmware/motion.py`: no guard for `rate <= 0` (the parser rejects it); add an assert. `START_RATE` and `accel` are not settings; expose them if tuning needs it. Add triangle-profile and acceleration tests.

### App: configuration and controller
- [ ] `app/config.py`: `Settings.load` raises on corrupt JSON or a non-dict; catch and fall back to defaults with a message.
- [ ] `app/config.py`: `save` is not atomic and does not create the parent directory; write a temp file, `os.replace`, and `mkdir`.
- [ ] `app/controller.py`: `startswith("ERR")` also matches `ERRX`; compare to `"ERR"` or `"ERR "`. A partial line reads as "unexpected"; fine, but note it.
- [ ] `tests/test_controller.py`: add `set_light` and `wind` ERR paths and `close()`.

### App: detection, post-processing, camera
- [ ] `app/align.py`: the `m00` division is guarded only by `sprocket_min_area_frac > 0`; guard `m00 == 0` explicitly. The bright-picture test checks `cy` only; assert `cx`.
- [ ] `app/postprocess.py`: `resize_to` distorts if the aspect differs (user-chosen); warn or keep aspect. The denoise test only checks the output differs; assert on noise level.
- [ ] `app/camera.py`: the 2 s white-balance settle is hardcoded; make it a setting. Exposure controls apply a few frames late; discard frames after `set_exposure` if seen on the Pi. Verify `lock_white_balance` (called only from `__main__`) on the Pi.

### App: scan loop and runner
- [ ] `app/scan.py`: wind slack (`on_spool`, `to_wind`) is lost on resume; store it in `scan.json`.
- [ ] `app/scan.py`: `pause()`/`resume()` state is unguarded, and `pause()` before `run()` shows state `running`; guard state changes and set the state in `pause()`.
- [ ] `app/scan.py`: `slots.acquire()` has no timeout; add a timeout and raise `ScanError`.
- [ ] `app/scan.py`: the preview aspect uses the raw frame when `resize_to` is set; use `aligned.shape`.
- [ ] `app/scan.py`: `frame_number` and `scan.json` frames count a lost write frame, so resume can reuse its number; resume from `next_frame_number`.
- [ ] `app/scan.py`: mid-run saves record a stale state after a hard crash and can leave a `.tmp` file; clean the `.tmp` on load.
- [ ] `app/scan.py`: a write failure is noticed one loop late; reap after submit.
- [ ] `tests/test_scan.py`: add flag-time and wind-time save tests; make the "finishing" window not timing dependent.
- [ ] `app/runner.py`: `pause()`/`resume()` check-then-act can overwrite `done`/`error` with `paused`; take the scanner state under a lock. Same cause: `status()` reads several fields non-atomically.
- [ ] `app/runner.py`: `Scanner(...)` mkdir `OSError` escapes `start()`; map it to `RunnerError`.
- [ ] `app/runner.py`: the test-frame preview stays cached after `set_light`/`set_exposure`; clear `_test_preview` there.
- [ ] `app/runner.py`: the light turns on while paused-before-run; set the light after the pause check.

### Web server and page
- [ ] `app/static/index.html`: success text shows in the error colour; use a separate class.
- [ ] `app/static/index.html`: a 422 detail list shows only "request failed (422)"; print the detail.
- [ ] `app/static/index.html`: the slider stays at a rejected value after a 409; reload settings.
- [ ] `app/static/index.html`: broken preview image before the first frame; hide until loaded.
- [ ] `app/static/index.html`: the status error class is stale after a poll failure; clear it on success.
- [ ] `app/static/index.html`: buttons are always enabled; disable by state.
- [ ] `app/server.py`: non-`RunnerError` hardware exceptions give a plain 500; map to a JSON error.
- [ ] `tests/test_server.py`: the gate test relies on a thread name; the 10 s gate timeout slows a regression failure; use an event and a short timeout.

### Entrypoint and repo
- [ ] `.gitignore`: stray `*.FCStd1` rule; remove. `*.png`/`*.jpg` rules would hide images added under `app/static`; add `!app/static/**` if needed.
- [ ] `requirements.txt`: unpinned; pin once the Pi install works.

### Not run on hardware (bring-up checklist)
- [ ] Pico flashing and serial check (Task 4).
- [ ] Pi camera capture (Task 9).
- [ ] End-to-end check on the machine (Task 14).
- [ ] Encode a first MP4 on a desktop with `tools/encode_reel.py` from a real test scan (only synthetic PNGs have been encoded so far).
- [ ] Test each GPU encoder on real hardware: `nvenc`, `qsv`, `amf` and `vaapi` (both codecs) and `hevc_videotoolbox` have never been run (pytest only checks the command text). `h264_videotoolbox`, `libx264` and `libx265` were run on one Mac with synthetic frames only.
- [ ] Verify the default quality value per encoder on a real scan (`cpu` 15 is the legacy value; `nvenc` 19, `qsv` 20, `amf` 18, `vaapi` 20 are unverified guesses, `videotoolbox` 65 is only known to be accepted).
- [ ] The web page in a browser.

Process note: commit trailers name the model that wrote each commit (Haiku 5.5 or Sonnet 5.5). The plan text for Tasks 10, 12 and 13 is out of date, because the code changed in fix rounds.

## 5. Before selling anything

- Licence: the code is GPL-3.0. Source must be offered with each unit and the licence stays GPL. A different licence needs a clean-room rewrite or permission from all authors.
- Lens: source a new (not used) lens; the microscope lens may be discontinued.
- Certification: CE/FCC.
- Security: the web UI has no login.
- [ ] Check Host/Origin (configurable allowlist) before exposing the app beyond a trusted LAN (no CORS means JSON routes are safe from other web pages, but routes without a body such as stop/pause/resume/test-frame can be triggered by a form post, and there is no Host check against DNS rebinding).
- Price and support plan.

## 6. Open questions

- Pi 4 (2 GB) vs Pi 5: is capture and alignment fast enough on the Pi 4?
- Is the microscope lens sharp enough across the full frame, and is it still available from retailers? The fallback is an enlarger lens.
