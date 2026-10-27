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

The Pi never drives motors or the LED directly. It sends one text command per line and waits for the reply (`OK` or `ERR ...`) before sending the next.

## 2. Components

| Module | Responsibility | Depends on |
|---|---|---|
| `app/__main__.py` | Entrypoint: load settings, open controller and camera, lock white balance, start uvicorn on `0.0.0.0:8000` (`--config`, `--port`) | `config`, `controller`, `camera`, `runner`, `server` |
| `app/config.py` | `Settings` dataclass with defaults; `load` ignores unknown keys, `save` writes JSON | stdlib |
| `app/controller.py` | Serial wrapper: `advance`, `wind`, `set_light`, `status`; blocks until the reply; raises `ControllerError` | `pyserial` (imported in `open`) |
| `app/camera.py` | `Picamera2Camera`: full-resolution still capture as a BGR array, fixed exposure and gain, one-time white-balance lock | `picamera2` |
| `app/align.py` | `detect_sprocket` (centre of the bright hole in the left strip), `align_offset`, `shift_frame` (whole-pixel shift, black fill) | OpenCV, NumPy |
| `app/postprocess.py` | Opt-in denoise and resize (both off by default) | OpenCV |
| `app/takeup.py` | `wind_steps`: motor steps to wind N frames onto the spool given how much is already on it | stdlib |
| `app/scan.py` | `Scanner`: the scan loop, pause/resume/stop, background PNG writes, `scan.json` persistence | `align`, `postprocess`, `takeup`, OpenCV |
| `app/video.py` | `build_mp4`: ffmpeg encode of `frames/` into `reel.mp4` | `ffmpeg` binary |
| `app/runner.py` | `ScanRunner`: runs a `Scanner` on a thread, validates the reel name, builds the video afterwards, serves preview/test-frame/light/exposure only while idle | `scan`, `align`, `video` |
| `app/server.py` | FastAPI routes and the page `app/static/index.html` | `runner` |
| `firmware/protocol.py` | `parse_command`, `format_ok`, `format_err`; pure Python, tested on a PC | none |
| `firmware/motion.py` | `step_delays_us`: trapezoid speed profile, pure Python | none |
| `firmware/pins.py` | GPIO numbers | none |
| `firmware/main.py` | MicroPython loop: read a line, parse, move a motor or set the LED, reply | `machine`, the three modules above |

Web routes: `GET /`, `GET /api/status`, `GET /api/settings`, `POST /api/scan/start|pause|resume|stop`, `GET /api/preview.jpg`, `POST /api/test-frame`, `POST /api/light`, `POST /api/exposure`.

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

Before the loop, the light is set to `light_percent`. Each pass:

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

When the loop ends, pending writes finish, the light is turned off, and `scan.json` is saved. State is `done` or `error`. `ScanRunner` then builds `reel.mp4` if the state is `done`.

## 5. Alignment

The target is set once, from the first frame where the hole is detected (its x position and half the image height). The film is physically nudged until the hole is within `nudge_tolerance_frac` of the image height from the target row; `shift_frame` removes the small residual. The shift is an integer pixel copy into a same-size black canvas: no resampling, so no blur, and no crop. Areas shifted in from outside the capture are black; the sprocket hole and film edges stay in the picture. On resume, the target is read back from `scan.json` so a continued reel matches the earlier frames.

## 6. Output layout

```
scans/<reel name>/
  frames/frame_00000000.png, frame_00000001.png, ...
  reel.mp4        (ffmpeg, libx264, crf 15, yuv420p, at `fps`, default 18)
  scan.json       (settings, target, frame count, flagged frames, state)
```

The reel name is 1-64 letters, digits, `-` or `_`. Starting a scan with an existing name continues from the next unused frame number. `scan.json` is written to a temporary file and renamed, so it is never half written. Odd image dimensions are rounded down to even for the MP4 (`yuv420p` needs even sizes).

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
| `light_percent` | 100 | LED brightness |
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
| Sprocket lost | `max_consecutive_failures` (5) frames in a row without a hole raises `ScanError: sprocket hole lost`. State becomes `error`, the light is turned off. |
| Too many nudges | More than `max_nudges` (25) nudges for one frame raises `ScanError`. State `error`. |
| Controller silent or `ERR` | `ControllerError` ("no reply ... (timeout)" after `serial_timeout_s`, or the `ERR` text, or an unexpected reply). Caught by the loop: state `error`, message in `status`. Frames already written stay on disk and the reel can be continued by starting with the same name. |
| Write failure | The failed frame number is flagged. The loop notices on the next pass (or at the end), raises "frame write failed", and the error text lists each failure. |
| `scan.json` cannot be saved | Added to the error message, state `error`. |
| Video build fails (ffmpeg missing or failing) | Frames are kept; `status.video` shows `error: ...`. |
| Action while a scan runs (preview grab, test frame, light, exposure, second start) | `RunnerError`, HTTP 409. A bad reel name gives HTTP 400. |

In every ending the Scanner tries to turn the light off; a failure there is ignored because the controller may be what failed.
