# Architecture

This describes the code as committed on `feature/scanner-refinement`. The design decisions behind it are in `docs/superpowers/specs/2026-10-27-scanner-refinement-design.md`.

## 1. Overview

```
 Browser (phone / laptop)
        |  HTTP, LAN only, no login
        v
+---------------------------------------------+
| Raspberry Pi                                |
|   app/ (FastAPI web UI + scan loop)         |
|   HQ camera (picamera2, CSI cable)          |
+----------------------+----------------------+
                       | USB serial, 115200 baud, line commands
                       v
+---------------------------------------------+
| RP2040 (Pico), MicroPython firmware/        |
+-----+------------------+------------------+-+
      | STEP/DIR/EN      | STEP/DIR/EN      | PWM 20 kHz
      v                  v                  v
  TMC2209 (film)    TMC2209 (reel)         LED driver
      |                  |
  film stepper      take-up stepper
```

The LED driver link carries 20 kHz PWM in the current firmware, but the app uses it only when `light_control` is true and the LED driver supports PWM dimming. With the default (`light_control` false) the LED is simply on whenever it is powered: the app does not control it and never switches it off. Caveat (when `light_control` is true): with a PWM-dimmable driver such as the RCD-24 (not the lean build's driver), `LIGHT 0` can be full on; see `wiring.md` section 6.

The Pi never drives motors or the LED directly. It sends one text command per line and waits for the reply (`OK` or `ERR ...`) before sending the next.

## 2. Components

| Module | Responsibility | Depends on |
|---|---|---|
| `app/__main__.py` | Entrypoint: load settings, create the `CommandLog`, open controller (traffic goes to the log) and camera, lock white balance, start uvicorn on `0.0.0.0:8000` (`--config`, `--port`); on exit it stops the scan, turns the light off when `light_control` is on (caveat: with a PWM-dimmable driver such as the RCD-24 (not the lean build's driver), `LIGHT 0` can be full on; see `wiring.md` section 6) and closes the controller and camera | `config`, `controller`, `camera`, `runner`, `server` |
| `app/config.py` | `Settings` dataclass with defaults; `load` ignores unknown keys, `save` writes JSON | stdlib |
| `app/controller.py` | Serial wrapper: `advance`, `wind`, `set_light`, `status`, `command` (operator line from the terminal); blocks until the reply; raises `ControllerError`; reports each command, reply and error to `on_traffic` | `pyserial` (imported in `open`) |
| `app/console.py` | `CommandLog`: thread-safe ring of the last 500 entries (`cmd`, `reply`, `event`, `error`) with ids that never repeat | stdlib |
| `app/camera.py` | `Picamera2Camera`: full-resolution still capture as a BGR array, fixed exposure and gain, one-time white-balance lock | `picamera2` |
| `app/align.py` | `detect_sprocket` (centre of the bright hole in the left strip), `align_offset`, `shift_frame` (whole-pixel shift, black fill) | OpenCV, NumPy |
| `app/postprocess.py` | Opt-in denoise and resize (both off by default) | OpenCV |
| `app/takeup.py` | `wind_steps`: motor steps to wind N frames onto the spool given how much is already on it | stdlib |
| `app/scan.py` | `Scanner`: the scan loop, pause/resume/stop, background PNG writes, `scan.json` persistence, `on_event` text for the log | `align`, `postprocess`, `takeup`, OpenCV |
| `app/runner.py` | `ScanRunner`: runs a `Scanner` on a thread, validates the reel name, serves preview/test-frame/light/exposure/console only while idle, logs UI actions, reports status | `scan`, `align`, `console` |
| `app/server.py` | FastAPI routes and the page `app/static/index.html` | `runner` |
| `firmware/protocol.py` | `parse_command`, `format_ok`, `format_err`; pure Python, tested on a PC | none |
| `firmware/motion.py` | `step_delays_us`: trapezoid speed profile, pure Python | none |
| `firmware/pins.py` | GPIO numbers | none |
| `firmware/main.py` | MicroPython loop: read a line, parse, move a motor or set the LED, reply | `machine`, the three modules above |

Web routes (`POST /api/light` and console `LIGHT` are refused with 400 unless `light_control` is true): `GET /`, `GET /api/status`, `GET /api/settings`, `POST /api/scan/start|pause|resume|stop`, `GET /api/preview.jpg`, `POST /api/test-frame`, `POST /api/light`, `POST /api/exposure`, `GET /api/log?since=<id>`, `POST /api/console`.

`GET /api/status` returns `state` (`idle`, `running`, `paused`, `finishing`, `done`, `error`), `name`, `frame`, `flagged` (count), `error`, and also `flagged_frames` (the last 50 flagged frame numbers), `elapsed_s` (since the scan started, 0 when idle), `rate_fps` (frames per second over the last 30 s, 0 unless running), `disk_free_gb` (free space on the output drive) and `target_frac` (`[x, y]` of the alignment target as fractions of the frame, `null` until known).

### Log and terminal

One `CommandLog` (last 500 entries in memory, lost on restart) collects: every controller command (`cmd`) before it is written, every good reply (`reply`), every controller failure (`error`, just before `ControllerError` is raised), scan events (`event`: start, target set, each nudge, flagged frames, winds, pause, resume, stop, done or error; nothing per good frame) and UI actions (`event`: light, exposure, test frame). Each entry is `{"id", "t", "kind", "text"}`; ids start at 1 and keep counting when old entries drop. `GET /api/log?since=N` returns `{"entries": [...], "last_id": n}` with only entries newer than `N`; the page polls it every 0.7 s (3 s when the tab is hidden). No route clears the log; the page's Clear hides lines in that browser only.

`POST /api/console` with `{"command": "..."}` (1-40 characters) sends one line to the controller and returns `{"reply": "<text after OK>"}`. Only `ADVANCE`, `WIND`, `LIGHT` and `STATUS` are accepted (case-insensitive, printable ASCII, no newline); anything else is HTTP 400 `unknown command`. `ADVANCE` and `WIND` take integer steps (at most 20,000) and a rate of 1-4000 (default 2000 or 1500), and a move may last at most 15 s (steps / rate); `LIGHT` takes one integer 0-100 and `STATUS` none. Anything else is HTTP 400. A move cannot be stopped from the app: the firmware blocks until it ends. It is refused with 409 while a scan runs, and a controller failure is 502 (its text is already in the log).

## 3. Controller protocol

Lines end with `\n`. Commands are case-insensitive. Rates are steps per second; the default rate is `ADVANCE` 2000, `WIND` 1500, the maximum is 4000. A negative step count reverses the motor.

| Command | Reply | Example |
|---|---|---|
| `ADVANCE <steps> [rate]` | `OK` when the film move has finished | `ADVANCE 164` -> `OK` |
| `WIND <steps> [rate]` | `OK` when the take-up move has finished | `WIND 100 1500` -> `OK` |
| `LIGHT <0-100>` | `OK` | `LIGHT 30` -> `OK` |
| `STATUS` | `OK light=<percent>` | `STATUS` -> `OK light=30` |
| anything else or bad arguments | `ERR <message>` (`empty`, `bad steps`, `bad rate`, `bad percent`, `rate out of range`, `percent out of range`, `unknown command`, or a `usage: ...` line) | `FOO` -> `ERR unknown command` |

The film motor keeps its coil energised after a move (it holds position); the reel motor is released after each move.

## 4. The scan loop (`Scanner.run` in `app/scan.py`)

Before the loop, the light is set to `light_percent` (only when `light_control` is true; otherwise the app never touches the light). Each pass:

1. Stop if `stop()` was called or `max_frames` is reached. Wait while paused.
2. Check finished background writes; if one failed, raise `ScanError("frame write failed")`.
3. Capture a frame (flipped vertically if `flip_vertical`) and detect the sprocket hole. If it is not found, capture again and retry up to `retries` times.
4. If found and no target exists yet, set the target to the detected centre x and half the image height, and save `scan.json`.
5. Nudge: if the hole is further than `nudge_tolerance_frac` of the image height from the target row, count a nudge. Over `max_nudges` in a row raises `ScanError`. Otherwise move the film `nudge_forward_steps` (hole below target) or `nudge_reverse_steps` (hole above) at `nudge_rate`, and go back to step 1 without saving a frame.
6. If within tolerance, store the residual offset and reset the consecutive-failure count. If the hole was not found after the retries, count a failure (`max_consecutive_failures` in a row raises "sprocket hole lost"), flag this frame number, and keep the previous offset.
7. Shift: `shift_frame` moves the frame by the whole-pixel offset, then `postprocess` applies the optional denoise and resize.
8. Write: update the preview, then queue `frame_XXXXXXXX.png` for a worker thread (at most 4 pending writes, so memory stays bounded). Count the frame, reset the nudge count.
9. Wind: after `frames_per_wind + 3` frames are waiting, wind `frames_per_wind` frames of film onto the spool (`wind_steps` at `wind_rate`), leaving a little slack, and save `scan.json`.
10. Advance one frame (`steps_per_frame` at `advance_rate`) and report progress.

When the loop ends, pending writes finish, the light is turned off when `light_control` is true (caveat: with a PWM-dimmable driver such as the RCD-24 (not the lean build's driver), `LIGHT 0` can be full on; see `wiring.md` section 6), and `scan.json` is saved. State is `done` or `error`. While that happens the runner reports `finishing`, never `done`, so `done` means the frames and `scan.json` are on disk.

## 5. Alignment

The target is set once, from the first frame where the hole is detected (its x position and half the image height). The film is physically nudged until the hole is within `nudge_tolerance_frac` of the image height from the target row; `shift_frame` removes the small residual. The shift is an integer pixel copy into a same-size black canvas: no resampling, so no blur, and no crop. Areas shifted in from outside the capture are black; the sprocket hole and film edges stay in the picture. On resume, the target is read back from `scan.json` so a continued reel matches the earlier frames.

## 6. Output layout

```
scans/<reel name>/
  frames/frame_00000000.png, frame_00000001.png, ...
  scan.json       (settings, target, frame count, flagged frames, state)
```

The reel name is 1-64 letters, digits, `-` or `_`. Starting a scan with an existing name continues from the next unused frame number. `scan.json` is written to a temporary file and renamed, so it is never half written.

## 6a. Encoding on a computer

The device only collects frames; they are the master. `tools/encode_reel.py REEL_DIR` turns them into `reel.mp4` on a desktop with `ffmpeg` installed (standard library only; the app never imports it).

- Encoders: `cpu` (libx264/libx265), `nvenc`, `videotoolbox`, `qsv`, `amf`, `vaapi`, each for H.264 or HEVC. `--encoder auto` reads `ffmpeg -encoders`, tries the hardware ones in that order, and falls back to the next if one exits non-zero in its first seconds or reports an init error. The CPU encoder is always last. A named encoder never falls back.
- Quality is one number per encoder (`cpu` CRF 15 with `-preset slower`; the others map to their constant-quality flag, see the README). Frames are scaled to even dimensions (`scale=trunc(iw/2)*2:trunc(ih/2)*2`), or `scale=-2:H` with `--height`.
- If frame numbers are missing between the first and last, the tool warns and feeds ffmpeg a temporary concat list of the frames that exist (each shown for 1/fps), so timing stays even.
- Progress comes from `ffmpeg -progress pipe:1`, printed at most once a second. `--dry-run` prints the command; `--list-encoders` shows what the ffmpeg offers.
- Testing: pytest covers command building for every encoder and codec, encoder ordering, `ffmpeg -encoders` parsing, gap detection, the concat list, progress parsing, fallback and the CLI, all with injected runners. Only these have been run, by hand, on one Mac with synthetic frames and never on a real scan: `libx264`, `libx265` and `h264_videotoolbox`. `hevc_videotoolbox` and every NVIDIA (nvenc), Intel (qsv), AMD (amf) and VAAPI encoder, for both H.264 and HEVC, have not been run. Default quality values for the hardware encoders are unverified.
- Output: ffmpeg writes `<name>.part.mp4` next to the final file and the tool renames it over the output only on success, so a failed run never removes or damages an existing `reel.mp4`; a successful run replaces it.

By hand, for the CPU path:

```
ffmpeg -framerate 18 -start_number 0 -i frames/frame_%08d.png -vf scale=trunc(iw/2)*2:trunc(ih/2)*2 -c:v libx264 -preset slower -crf 15 -pix_fmt yuv420p reel.mp4
```

Use 18 fps for Super 8 sound-speed playback (24 fps silent speed is not used here). The PNGs are 4056x3040. A smaller copy for sharing can use `-vf scale=-2:1080`. DaVinci Resolve can also import the PNG sequence.

## 7. Calibration-critical settings (defaults from `app/config.py`)

| Setting | Default | Meaning |
|---|---|---|
| `steps_per_frame` | 164 | Film motor steps for one frame pitch |
| `advance_rate` | 2000 | Steps per second for a frame advance |
| `nudge_forward_steps` / `nudge_reverse_steps` | 15 / -5 | Correction moves |
| `nudge_rate` | 170 | Steps per second while nudging |
| `nudge_tolerance_frac` | 0.03 | Allowed hole error, fraction of image height |
| `max_nudges` | 25 | Nudges in a row before the scan stops |
| `reel_steps_per_rev` | 3200 | Take-up motor steps per spool revolution |
| `wind_rate` | 1500 | Steps per second for winding |
| `frames_per_wind` | 8 | Frames taken up per wind |
| `frame_height_mm`, `film_thickness_mm`, `spool_inner_diameter_mm` | 4.01, 0.15, 32.0 | Spool geometry used by `wind_steps` |
| `exposure_us`, `gain` | 2000, 1.0 | Fixed camera exposure |
| `flip_vertical` | true | Flip captures so nudges go the right way |
| `light_control` | false | False: fixed-brightness LED, which is simply on whenever it is powered; the app does not control it and never switches it off (it stays lit after a scan until the supply is switched off). The app never sends `LIGHT` (not at start-up, scan start, scan end or exit, nor for the test frame), `POST /api/light` and console `LIGHT` give HTTP 400 `light control is disabled`, `GET /api/settings` reports it and the page hides the slider and the `LIGHT` help line. True (dimmable LED and firmware PWM on GPIO 15): behaviour as described elsewhere in this document. Old config files without it load as false |
| `light_percent` | 100 | LED brightness (used only when `light_control` is true) |
| `sprocket_strip_frac` | 0.16 | Left fraction of the image searched for the hole |
| `sprocket_threshold` | 230 | Brightness (0-255) that counts as the hole |
| `sprocket_min_area_frac` / `sprocket_max_area_frac` | 0.012 / 0.06 | Accepted hole area, fraction of the detection image |
| `detect_width` | 1024 | Width the image is scaled to for detection |
| `retries` | 3 | Extra captures when the hole is not found |
| `max_consecutive_failures` | 5 | Frames in a row without a hole before the scan stops |
| `serial_port`, `baudrate`, `serial_timeout_s` | `/dev/ttyACM0`, 115200, 30.0 | Controller link; the timeout must exceed the longest move |
| `denoise`, `resize_to` | false, none | Opt-in post-processing |

Settings are read from the JSON file at start. The web UI changes light and exposure in the running app only; they are recorded in each reel's `scan.json` but not written back to `scanner.json`.

## 8. Error handling

| Situation | What happens |
|---|---|
| Sprocket not found | Recapture up to `retries` times. If still missing, the frame is saved with the previous offset, its number is added to `flagged` in `scan.json`, and the scan continues. |
| Sprocket lost | `max_consecutive_failures` (5) frames in a row without a hole raises `ScanError: sprocket hole lost`. State becomes `error`, the light is turned off if `light_control` is true (see the PWM-driver caveat below). |
| Too many nudges | More than `max_nudges` (25) nudges for one frame raises `ScanError`. State `error`. |
| Controller silent or `ERR` | `ControllerError` ("no reply ... (timeout)" after `serial_timeout_s`, or the `ERR` text, or an unexpected reply). Caught by the loop: state `error`, message in `status`. Frames already written stay on disk and the reel can be continued by starting with the same name. |
| Write failure | The failed frame number is flagged. The loop notices on the next pass (or at the end), raises "frame write failed", and the error text lists each failure. |
| `scan.json` cannot be saved | Added to the error message, state `error`. |
| Action while a scan runs (preview grab, test frame, light, exposure, console command, second start) | `RunnerError`, HTTP 409. A bad reel name or an unknown console command gives HTTP 400; a controller failure on a console command gives 502. |

In every ending, when `light_control` is true, the Scanner tries to turn the light off; a failure there is ignored because the controller may be what failed. Caveat: with a PWM-dimmable driver such as the RCD-24 (not the lean build's driver), `LIGHT 0` can be full on; see `wiring.md` section 6.
