# Super 8 Scanner Refinement: Firmware and App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the loose Marlin + script setup with an RP2040 controller firmware and a single Pi web app that scans a reel into aligned, uncropped frames plus an MP4.

**Architecture:** An RP2040 (MicroPython) runs a tiny line protocol (`ADVANCE`, `WIND`, `LIGHT`, `STATUS`) and drives two TMC2209 steppers and an LED PWM. A Python package `app/` on the Pi (controller client, camera, sprocket alignment, scan loop, ffmpeg, FastAPI web UI) replaces the scripts, which move to `legacy/`. Alignment is a lossless integer pixel shift (no crop, no resample).

**Tech Stack:** Python 3.11+ (Pi OS Bookworm), MicroPython on RP2040, OpenCV, numpy, picamera2, pyserial, FastAPI + uvicorn, ffmpeg, pytest.

**Spec:** `docs/superpowers/specs/2026-10-27-scanner-refinement-design.md`

**Scope of this plan:** firmware and software only, the parts that can be tested without the hardware. The enclosure/mechanics CAD, the controller PCB (KiCad) and the lighting build are separate plans. Until the PCB exists, the firmware runs on a Pi Pico on perfboard with two TMC2209 modules.

## Global Constraints

- GPL-3.0 stays: the app builds on existing GPL code (sprocket detection, spool maths); keep the `LICENSE` file and the original copyright notices in `legacy/`.
- Denoise and resize are off by default and are opt-in settings. Frames are aligned but never cropped; sprocket hole and film edges stay in the saved frame.
- The web UI is served by the Pi over the LAN; there is no on-device screen and no authentication in v1 (trusted home network only).
- Camera: Raspberry Pi HQ Camera (IMX477), 4056x3040, `picamera2`. Pi 4 (2 GB) is the default target.
- Controller protocol is line based ASCII at 115200 baud: `ADVANCE <steps> [rate]`, `WIND <steps> [rate]`, `LIGHT <0-100>`, `STATUS`; replies `OK [text]` after the move completes, or `ERR <reason>`.
- Saved output per reel: `frames/frame_00000000.png`..., `reel.mp4` (18 fps, ffmpeg), `scan.json`.
- Hardware-dependent numbers (steps per frame, rates, nudges) are settings with calibration defaults, not constants.
- Tests run with `pytest` from the repo root using the dev dependencies; hardware-only code is checked with the manual steps given in its task.

## File Structure

```
legacy/                      existing scripts, moved untouched (git mv Python legacy)
firmware/
  protocol.py                parse command lines, format replies (pure Python)
  motion.py                  trapezoid step-delay generator (pure Python)
  pins.py                    GPIO pin map
  main.py                    MicroPython glue: serial loop, motors, LED
app/
  __init__.py
  config.py                  Settings dataclass + JSON load/save
  controller.py              serial client for the RP2040
  align.py                   detect_sprocket, align_offset, shift_frame
  postprocess.py             opt-in denoise and resize
  takeup.py                  take-up spool wind steps
  camera.py                  picamera2 wrapper
  scan.py                    Scanner: the scan loop, resume, flagging
  video.py                   ffmpeg command and MP4 build
  runner.py                  ScanRunner: background scan, preview, test frame
  server.py                  FastAPI app
  static/index.html          the web page
  __main__.py                python -m app entrypoint
tests/
  helpers.py                 synthetic frame generator
  fakes.py                   FakeFilm (fake camera + controller)
  test_*.py
pytest.ini  requirements.txt  requirements-dev.txt
```

---

### Task 1: Repo reorganisation and test tooling

**Files:**
- Move: `Python/` to `legacy/`
- Create: `pytest.ini`, `requirements.txt`, `requirements-dev.txt`, `app/__init__.py`, `tests/test_smoke.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `pytest` runs from the repo root; `app` is importable; `firmware/` is on the import path (so tests can `import protocol`).

- [ ] **Step 1: Move the scripts and create the skeleton**

```bash
git mv Python legacy
mkdir -p app/static firmware tests
touch app/__init__.py
printf 'scans/\n.venv/\n__pycache__/\n.pytest_cache/\n' >> .gitignore
```

- [ ] **Step 2: Write the config files**

```ini pytest.ini
[pytest]
pythonpath = . firmware
testpaths = tests
```

```text requirements.txt
fastapi
uvicorn
pyserial
```

```text requirements-dev.txt
-r requirements.txt
pytest
httpx
numpy
opencv-python-headless
```

- [ ] **Step 3: Write a smoke test**

```python tests/test_smoke.py
import app


def test_app_package_imports():
    assert app is not None
```

- [ ] **Step 4: Install dev dependencies and run**

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
```
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "chore: move scripts to legacy/, add app skeleton and pytest config"
```

---

### Task 2: Firmware protocol parser

**Files:**
- Create: `firmware/protocol.py`
- Test: `tests/test_protocol.py`

**Interfaces:**
- Produces: `parse_command(line: str) -> tuple` returning `("ADVANCE", steps:int, rate:int)`, `("WIND", steps:int, rate:int)`, `("LIGHT", percent:int)` or `("STATUS",)`; raises `ProtocolError`. `format_ok(extra: str = "") -> str`, `format_err(message: str) -> str`. Constants `DEFAULT_RATE = {"ADVANCE": 2000, "WIND": 1500}`, `MAX_RATE = 4000`.

- [ ] **Step 1: Write the failing test**

```python tests/test_protocol.py
import pytest
from protocol import ProtocolError, format_err, format_ok, parse_command


def test_advance_uses_default_rate():
    assert parse_command("ADVANCE 164") == ("ADVANCE", 164, 2000)


def test_advance_with_rate_and_negative_steps():
    assert parse_command("advance -5 170\n") == ("ADVANCE", -5, 170)


def test_wind_default_rate():
    assert parse_command("WIND 1021") == ("WIND", 1021, 1500)


def test_light_and_status():
    assert parse_command("LIGHT 50") == ("LIGHT", 50)
    assert parse_command("STATUS") == ("STATUS",)


@pytest.mark.parametrize("line", [
    "", "   ", "FOO", "ADVANCE", "ADVANCE x", "ADVANCE 1 0", "ADVANCE 1 4001",
    "ADVANCE 1 2 3", "LIGHT", "LIGHT 101", "LIGHT -1", "LIGHT x", "STATUS now",
])
def test_bad_lines_raise(line):
    with pytest.raises(ProtocolError):
        parse_command(line)


def test_formatting():
    assert format_ok() == "OK"
    assert format_ok("light=50") == "OK light=50"
    assert format_err("bad") == "ERR bad"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_protocol.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'protocol'`)

- [ ] **Step 3: Write the implementation**

```python firmware/protocol.py
# Line protocol between the Pi and the RP2040. Pure Python so it runs on
# MicroPython and in host tests.

DEFAULT_RATE = {"ADVANCE": 2000, "WIND": 1500}  # steps per second
MAX_RATE = 4000


class ProtocolError(Exception):
    pass


def _int(text, name):
    try:
        return int(text)
    except ValueError:
        raise ProtocolError("bad " + name)


def parse_command(line):
    parts = line.strip().split()
    if not parts:
        raise ProtocolError("empty")
    name = parts[0].upper()
    args = parts[1:]
    if name in ("ADVANCE", "WIND"):
        if not 1 <= len(args) <= 2:
            raise ProtocolError("usage: %s <steps> [rate]" % name)
        steps = _int(args[0], "steps")
        rate = _int(args[1], "rate") if len(args) == 2 else DEFAULT_RATE[name]
        if not 1 <= rate <= MAX_RATE:
            raise ProtocolError("rate out of range")
        return (name, steps, rate)
    if name == "LIGHT":
        if len(args) != 1:
            raise ProtocolError("usage: LIGHT <0-100>")
        percent = _int(args[0], "percent")
        if not 0 <= percent <= 100:
            raise ProtocolError("percent out of range")
        return (name, percent)
    if name == "STATUS":
        if args:
            raise ProtocolError("usage: STATUS")
        return (name,)
    raise ProtocolError("unknown command")


def format_ok(extra=""):
    return "OK " + extra if extra else "OK"


def format_err(message):
    return "ERR " + message
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_protocol.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add firmware/protocol.py tests/test_protocol.py && git commit -m "feat(firmware): controller line protocol parser"
```

---

### Task 3: Firmware motion profile

**Files:**
- Create: `firmware/motion.py`
- Test: `tests/test_motion.py`

**Interfaces:**
- Produces: `step_delays_us(steps: int, rate: int, accel: int = 8000)` generator yielding the microsecond delay for each step (trapezoid ramp from 200 steps/s up to `rate` and back down). Uses `abs(steps)`; `START_RATE = 200`.

- [ ] **Step 1: Write the failing test**

```python tests/test_motion.py
from motion import START_RATE, step_delays_us


def test_zero_steps_yields_nothing():
    assert list(step_delays_us(0, 2000)) == []


def test_one_delay_per_step_and_sign_ignored():
    assert len(list(step_delays_us(164, 2000))) == 164
    assert len(list(step_delays_us(-164, 2000))) == 164


def test_ramp_is_symmetric_and_starts_slow():
    delays = list(step_delays_us(164, 2000))
    assert delays == delays[::-1]
    assert delays[0] == 1000000 // START_RATE


def test_long_move_cruises_at_rate_but_never_faster():
    delays = list(step_delays_us(1000, 2000))
    assert min(delays) == 500
    assert delays[500] == 500


def test_rate_below_start_rate_is_respected():
    assert min(step_delays_us(50, 170)) >= 1000000 // 170
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_motion.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'motion'`)

- [ ] **Step 3: Write the implementation**

```python firmware/motion.py
import math

START_RATE = 200  # steps per second at the start and end of every move


def step_delays_us(steps, rate, accel=8000):
    """Microseconds between steps for a trapezoid speed profile."""
    steps = abs(steps)
    for i in range(steps):
        d = min(i, steps - 1 - i)  # steps from the nearest end of the move
        v = min(rate, math.sqrt(START_RATE * START_RATE + 2 * accel * d))
        yield int(1000000 / v)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_motion.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add firmware/motion.py tests/test_motion.py && git commit -m "feat(firmware): trapezoid step delay generator"
```

---

### Task 4: Firmware main (MicroPython glue) and flashing

**Files:**
- Create: `firmware/pins.py`, `firmware/main.py`

**Interfaces:**
- Consumes: `parse_command`, `format_ok`, `format_err`, `ProtocolError` (Task 2); `step_delays_us` (Task 3).
- Produces: a board that answers the protocol on its USB serial port. `ADVANCE` holds the film motor energised afterwards (so the wheel does not drift); `WIND` releases the reel motor after the move.

This task is hardware glue and is verified manually, not by pytest.

- [ ] **Step 1: Write the pin map**

```python firmware/pins.py
# Pico GPIO numbers. Match these to the perfboard/PCB wiring.
FILM_STEP, FILM_DIR, FILM_EN = 2, 3, 4
REEL_STEP, REEL_DIR, REEL_EN = 5, 6, 7
SENSOR_IN = 14  # reserved for a frame/film-end sensor
LED_PWM = 15
```

- [ ] **Step 2: Write the firmware**

```python firmware/main.py
import sys
import time

from machine import PWM, Pin

import pins
from motion import step_delays_us
from protocol import ProtocolError, format_err, format_ok, parse_command

PULSE_US = 3  # TMC2209 needs >= 100 ns


class Motor:
    def __init__(self, step, direction, enable, hold):
        self.step = Pin(step, Pin.OUT, value=0)
        self.dir = Pin(direction, Pin.OUT, value=0)
        self.en = Pin(enable, Pin.OUT, value=1)  # TMC2209 EN is active low
        self.hold = hold

    def move(self, steps, rate):
        self.dir.value(1 if steps > 0 else 0)
        self.en.value(0)
        for delay in step_delays_us(steps, rate):
            self.step.value(1)
            time.sleep_us(PULSE_US)
            self.step.value(0)
            time.sleep_us(max(delay - PULSE_US, 1))
        if not self.hold:
            self.en.value(1)


film = Motor(pins.FILM_STEP, pins.FILM_DIR, pins.FILM_EN, hold=True)
reel = Motor(pins.REEL_STEP, pins.REEL_DIR, pins.REEL_EN, hold=False)

led = PWM(Pin(pins.LED_PWM))
led.freq(20000)  # above flicker and camera banding range
led.duty_u16(0)
light = 0


def set_light(percent):
    global light
    light = percent
    led.duty_u16(percent * 65535 // 100)


while True:
    line = sys.stdin.readline()
    try:
        cmd = parse_command(line)
        if cmd[0] == "ADVANCE":
            film.move(cmd[1], cmd[2])
            print(format_ok())
        elif cmd[0] == "WIND":
            reel.move(cmd[1], cmd[2])
            print(format_ok())
        elif cmd[0] == "LIGHT":
            set_light(cmd[1])
            print(format_ok())
        else:
            print(format_ok("light=%d" % light))
    except ProtocolError as e:
        print(format_err(str(e)))
```

- [ ] **Step 3: Check it compiles**

Run: `python3 -m py_compile firmware/main.py firmware/pins.py`
Expected: no output (it cannot be imported on a PC because `machine` is MicroPython only)

- [ ] **Step 4: Flash a Pico and check by hand**

```bash
pip install mpremote
mpremote cp firmware/protocol.py firmware/motion.py firmware/pins.py :
mpremote cp firmware/main.py :main.py
mpremote reset
```
Then from the Pi or PC (replace the port):
```bash
python3 - <<'EOF'
import serial
p = serial.Serial("/dev/ttyACM0", 115200, timeout=10)
for cmd in ["STATUS", "LIGHT 30", "STATUS", "ADVANCE 164", "WIND 100", "FOO"]:
    p.write((cmd + "\n").encode()); print(cmd, "->", p.readline().decode().strip())
EOF
```
Expected: `OK light=0`, `OK`, `OK light=30`, `OK` (film motor steps), `OK` (reel steps), `ERR unknown command`. The LED dims with `LIGHT`.

- [ ] **Step 5: Commit**

```bash
git add firmware/pins.py firmware/main.py && git commit -m "feat(firmware): MicroPython main loop for steppers and LED"
```

---

### Task 5: App settings

**Files:**
- Create: `app/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: dataclass `Settings` (all fields below, with defaults), `Settings.load(path) -> Settings` (defaults if the file is missing; unknown keys ignored; `resize_to` list becomes tuple), `settings.save(path)`.

- [ ] **Step 1: Write the failing test**

```python tests/test_config.py
from app.config import Settings


def test_defaults_keep_the_film_look():
    s = Settings()
    assert s.denoise is False
    assert s.resize_to is None
    assert s.steps_per_frame == 164


def test_missing_file_gives_defaults(tmp_path):
    assert Settings.load(tmp_path / "nope.json") == Settings()


def test_round_trip_and_unknown_keys(tmp_path):
    path = tmp_path / "scanner.json"
    s = Settings(steps_per_frame=170, resize_to=(3840, 2160))
    s.save(path)
    text = path.read_text().replace("{", '{"bogus": 1,', 1)
    path.write_text(text)
    loaded = Settings.load(path)
    assert loaded == s
    assert loaded.resize_to == (3840, 2160)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.config'`)

- [ ] **Step 3: Write the implementation**

```python app/config.py
import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional, Tuple


@dataclass
class Settings:
    # controller link
    serial_port: str = "/dev/ttyACM0"
    baudrate: int = 115200
    serial_timeout_s: float = 30.0
    output_dir: str = "scans"
    # film transport, in motor steps (calibrate on the machine)
    steps_per_frame: int = 164
    advance_rate: int = 2000
    nudge_forward_steps: int = 15
    nudge_reverse_steps: int = -5
    nudge_rate: int = 170
    nudge_tolerance_frac: float = 0.03  # of image height
    max_nudges: int = 25
    # take-up spool
    reel_steps_per_rev: int = 3200
    wind_rate: int = 1500
    frames_per_wind: int = 8
    frame_height_mm: float = 4.01
    film_thickness_mm: float = 0.15
    spool_inner_diameter_mm: float = 32.0
    # camera and light
    width: int = 4056
    height: int = 3040
    exposure_us: int = 2000
    gain: float = 1.0
    flip_vertical: bool = True
    light_percent: int = 100
    # sprocket detection
    sprocket_strip_frac: float = 0.16
    sprocket_threshold: int = 230
    sprocket_min_area_frac: float = 0.012
    sprocket_max_area_frac: float = 0.06
    detect_width: int = 1024
    retries: int = 3
    max_consecutive_failures: int = 5
    # output
    png_compression: int = 2
    fps: int = 18
    denoise: bool = False
    resize_to: Optional[Tuple[int, int]] = None

    @classmethod
    def load(cls, path):
        path = Path(path)
        if not path.exists():
            return cls()
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in json.loads(path.read_text()).items() if k in known}
        if isinstance(data.get("resize_to"), list):
            data["resize_to"] = tuple(data["resize_to"])
        return cls(**data)

    def save(self, path):
        Path(path).write_text(json.dumps(asdict(self), indent=2))
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py && git commit -m "feat(app): settings with JSON load/save"
```

---

### Task 6: Controller client

**Files:**
- Create: `app/controller.py`
- Test: `tests/test_controller.py`

**Interfaces:**
- Consumes: `Settings` (Task 5).
- Produces: `class ControllerError(Exception)`; `class Controller(port)` where `port` has `write(bytes)`, `readline() -> bytes`, `reset_input_buffer()`; `Controller.open(settings) -> Controller` (real pyserial); methods `advance(steps: int, rate: int | None = None)`, `wind(steps: int, rate: int | None = None)`, `set_light(percent: int)`, `status() -> str`, `close()`. Every call blocks until the board replies and raises `ControllerError` on `ERR`, silence or an unexpected reply.

- [ ] **Step 1: Write the failing test**

```python tests/test_controller.py
import pytest

from app.controller import Controller, ControllerError


class FakePort:
    def __init__(self, replies):
        self.replies = list(replies)
        self.written = []

    def reset_input_buffer(self):
        pass

    def write(self, data):
        self.written.append(data.decode())

    def readline(self):
        return (self.replies.pop(0) + "\n").encode() if self.replies else b""

    def close(self):
        pass


def test_commands_are_formatted():
    port = FakePort(["OK"] * 5)
    c = Controller(port)
    c.advance(164, 2000)
    c.advance(-5)
    c.wind(1021, 1500)
    c.wind(10)
    c.set_light(50)
    assert port.written == [
        "ADVANCE 164 2000\n", "ADVANCE -5\n", "WIND 1021 1500\n", "WIND 10\n", "LIGHT 50\n",
    ]


def test_status_returns_text_after_ok():
    assert Controller(FakePort(["OK light=50"])).status() == "light=50"


def test_err_reply_raises():
    with pytest.raises(ControllerError, match="rate out of range"):
        Controller(FakePort(["ERR rate out of range"])).advance(1, 99999)


def test_silence_raises_timeout():
    with pytest.raises(ControllerError, match="timeout"):
        Controller(FakePort([])).status()


def test_unexpected_reply_raises():
    with pytest.raises(ControllerError, match="unexpected"):
        Controller(FakePort(["hello"])).status()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_controller.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.controller'`)

- [ ] **Step 3: Write the implementation**

```python app/controller.py
class ControllerError(Exception):
    pass


class Controller:
    def __init__(self, port):
        self._port = port

    @classmethod
    def open(cls, settings):
        import serial

        return cls(serial.Serial(settings.serial_port, settings.baudrate, timeout=settings.serial_timeout_s))

    def _send(self, line):
        self._port.reset_input_buffer()
        self._port.write((line + "\n").encode("ascii"))
        reply = self._port.readline().decode("ascii", "replace").strip()
        if not reply:
            raise ControllerError("no reply to %r (timeout)" % line)
        if reply.startswith("ERR"):
            raise ControllerError("%s: %s" % (line, reply))
        if reply != "OK" and not reply.startswith("OK "):
            raise ControllerError("unexpected reply to %r: %r" % (line, reply))
        return reply[2:].strip()

    def _move(self, name, steps, rate):
        line = "%s %d" % (name, steps)
        if rate is not None:
            line += " %d" % rate
        self._send(line)

    def advance(self, steps, rate=None):
        self._move("ADVANCE", steps, rate)

    def wind(self, steps, rate=None):
        self._move("WIND", steps, rate)

    def set_light(self, percent):
        self._send("LIGHT %d" % percent)

    def status(self):
        return self._send("STATUS")

    def close(self):
        self._port.close()
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_controller.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add app/controller.py tests/test_controller.py && git commit -m "feat(app): serial controller client"
```

---

### Task 7: Sprocket detection and lossless alignment

**Files:**
- Create: `app/align.py`, `tests/helpers.py`
- Test: `tests/test_align.py`

**Interfaces:**
- Consumes: `Settings` (Task 5).
- Produces: `detect_sprocket(image: np.ndarray, settings) -> tuple[float, float] | None` (hole centre `(x, y)` in full-resolution pixels), `align_offset(centre, target) -> tuple[float, float]` (`target - centre`), `shift_frame(image, dx, dy) -> np.ndarray` (integer shift, same size, black fill, lossless). Test helper `make_frame(h=600, w=800, hole_cx=74, hole_cy=300, hole_w=100, hole_h=130, picture=120)` returning a BGR uint8 frame.

The detection port of the legacy `ProcessImage` was checked against `Sample_Images/Full_Frame_Sample.png`: threshold 230 on the left 16% finds one contour of about 2.6% of the image area, centred near (95, 394).

- [ ] **Step 1: Write the test helper and failing test**

```python tests/helpers.py
import numpy as np


def make_frame(h=600, w=800, hole_cx=74, hole_cy=300, hole_w=100, hole_h=130, picture=120):
    """BGR test frame: dark film edge, bright sprocket hole on the left, grey picture."""
    img = np.zeros((h, w, 3), np.uint8)
    img[:, int(w * 0.18):] = picture
    x0, y0 = hole_cx - hole_w // 2, hole_cy - hole_h // 2
    img[max(y0, 0):y0 + hole_h, max(x0, 0):x0 + hole_w] = 255
    return img
```

```python tests/test_align.py
from pathlib import Path

import cv2
import numpy as np
import pytest
from helpers import make_frame

from app.align import align_offset, detect_sprocket, shift_frame
from app.config import Settings

S = Settings()
SAMPLE = Path(__file__).parent.parent / "Sample_Images" / "Full_Frame_Sample.png"


def test_finds_hole_centre():
    cx, cy = detect_sprocket(make_frame(hole_cx=74, hole_cy=300), S)
    assert cx == pytest.approx(74, abs=1.5)
    assert cy == pytest.approx(300, abs=1.5)


def test_blank_frame_has_no_hole():
    assert detect_sprocket(np.zeros((600, 800, 3), np.uint8), S) is None


def test_small_bright_spot_is_rejected():
    img = np.zeros((600, 800, 3), np.uint8)
    img[100:110, 50:60] = 255
    assert detect_sprocket(img, S) is None


def test_bright_picture_area_is_ignored():
    cx, cy = detect_sprocket(make_frame(picture=200), S)
    assert cy == pytest.approx(300, abs=1.5)


def test_coordinates_are_full_resolution():
    img = make_frame(h=1200, w=1600, hole_cx=148, hole_cy=600, hole_w=200, hole_h=260)
    cx, cy = detect_sprocket(img, S)
    assert cx == pytest.approx(148, abs=3)
    assert cy == pytest.approx(600, abs=3)


def test_real_sample_frame():
    cx, cy = detect_sprocket(cv2.imread(str(SAMPLE)), S)
    assert cx == pytest.approx(95, abs=3)
    assert cy == pytest.approx(394, abs=3)


def test_zero_shift_is_identical():
    img = make_frame()
    assert np.array_equal(shift_frame(img, 0, 0), img)


def test_shift_moves_content_and_keeps_size():
    img = make_frame()
    out = shift_frame(img, -6, -20)  # keep the hole inside the detection strip
    assert out.shape == img.shape
    cx, cy = detect_sprocket(out, S)
    assert cx == pytest.approx(68, abs=1.5)
    assert cy == pytest.approx(280, abs=1.5)


def test_shift_fills_black_and_handles_huge_shift():
    img = make_frame(picture=200)
    assert not shift_frame(img, 0, 30)[:30].any()
    assert not shift_frame(img, 5000, 0).any()


def test_align_offset():
    assert align_offset((70.0, 310.0), (74.0, 300.0)) == (4.0, -10.0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_align.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.align'`)

- [ ] **Step 3: Write the implementation**

```python app/align.py
import cv2
import numpy as np


def detect_sprocket(image, settings):
    """Find the bright sprocket hole in the left strip; return its centre (x, y) in full-res pixels."""
    h, w = image.shape[:2]
    scale = min(1.0, settings.detect_width / w)
    small = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else image
    sh, sw = small.shape[:2]
    strip = small[:, : int(sw * settings.sprocket_strip_frac)]
    gray = cv2.cvtColor(cv2.GaussianBlur(strip, (5, 5), 0), cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, settings.sprocket_threshold, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    lo = sh * sw * settings.sprocket_min_area_frac
    hi = sh * sw * settings.sprocket_max_area_frac
    best = None
    for c in contours:
        area = cv2.contourArea(c)
        if lo <= area <= hi and (best is None or area > best[0]):
            best = (area, c)
    if best is None:
        return None
    m = cv2.moments(best[1])
    return (m["m10"] / m["m00"] / scale, m["m01"] / m["m00"] / scale)


def align_offset(centre, target):
    return (target[0] - centre[0], target[1] - centre[1])


def shift_frame(image, dx, dy):
    """Shift by whole pixels, same size, black fill. No resampling, so nothing is blurred or cropped."""
    dx, dy = int(round(dx)), int(round(dy))
    h, w = image.shape[:2]
    out = np.zeros_like(image)
    sx0, sx1 = max(0, -dx), min(w, w - dx)
    sy0, sy1 = max(0, -dy), min(h, h - dy)
    if sx1 > sx0 and sy1 > sy0:
        out[sy0 + dy:sy1 + dy, sx0 + dx:sx1 + dx] = image[sy0:sy1, sx0:sx1]
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_align.py -q`
Expected: all pass, including `test_real_sample_frame`. If that one fails, print the contours as in the check above and adjust `sprocket_threshold` or `sprocket_strip_frac` in `Settings`, not the test.

- [ ] **Step 5: Commit**

```bash
git add app/align.py tests/helpers.py tests/test_align.py && git commit -m "feat(app): sprocket detection and lossless frame shift"
```

---

### Task 8: Opt-in postprocess and spool take-up

**Files:**
- Create: `app/postprocess.py`, `app/takeup.py`
- Test: `tests/test_postprocess.py`, `tests/test_takeup.py`

**Interfaces:**
- Consumes: `Settings` (Task 5).
- Produces: `postprocess(image, settings) -> np.ndarray` (returns the same object when `denoise` is off and `resize_to` is `None`); `wind_steps(frames_on_spool: int, frames_to_add: int, settings) -> int` (motor steps, positive).

- [ ] **Step 1: Write the failing tests**

```python tests/test_postprocess.py
import numpy as np

from app.config import Settings
from app.postprocess import postprocess


def test_default_is_a_no_op():
    img = np.zeros((30, 40, 3), np.uint8)
    assert postprocess(img, Settings()) is img


def test_resize_is_opt_in():
    img = np.zeros((30, 40, 3), np.uint8)
    assert postprocess(img, Settings(resize_to=(80, 60))).shape[:2] == (60, 80)
    assert postprocess(img, Settings(resize_to=(20, 15))).shape[:2] == (15, 20)


def test_denoise_is_opt_in_and_changes_a_noisy_image():
    rng = np.random.default_rng(0)
    img = (128 + rng.normal(0, 20, (40, 40, 3))).clip(0, 255).astype(np.uint8)
    out = postprocess(img, Settings(denoise=True))
    assert out.shape == img.shape
    assert not np.array_equal(out, img)
```

```python tests/test_takeup.py
from app.config import Settings
from app.takeup import wind_steps


def test_empty_spool_first_eight_frames():
    # 8 frames * 4.01 mm on a 32 mm core = 114.9 degrees of 3200 steps/rev
    assert wind_steps(0, 8, Settings()) == 1021


def test_fuller_spool_needs_fewer_steps():
    s = Settings()
    assert wind_steps(3000, 8, s) < wind_steps(0, 8, s)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/test_postprocess.py tests/test_takeup.py -q`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write the implementations**

```python app/postprocess.py
import cv2


def postprocess(image, settings):
    """Opt-in denoise and resize. Both are off by default to keep the film look."""
    if settings.denoise:
        image = cv2.fastNlMeansDenoisingColored(image, None, 3, 3, 7, 29)
    if settings.resize_to:
        w, h = settings.resize_to
        upscaling = w * h > image.shape[1] * image.shape[0]
        image = cv2.resize(image, (w, h), interpolation=cv2.INTER_CUBIC if upscaling else cv2.INTER_AREA)
    return image
```

```python app/takeup.py
import math


def wind_steps(frames_on_spool, frames_to_add, settings):
    """Motor steps to take up `frames_to_add` frames, given how much film is already on the spool."""
    core_radius = settings.spool_inner_diameter_mm / 2
    tape_length = settings.frame_height_mm * frames_on_spool
    spool_radius = math.sqrt(tape_length * settings.film_thickness_mm / math.pi + core_radius ** 2)
    arc_length = frames_to_add * settings.frame_height_mm
    revolutions = arc_length / (2 * math.pi * spool_radius)
    return round(revolutions * settings.reel_steps_per_rev)
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/pytest tests/test_postprocess.py tests/test_takeup.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add app/postprocess.py app/takeup.py tests/test_postprocess.py tests/test_takeup.py && git commit -m "feat(app): opt-in postprocess and take-up spool maths"
```

---

### Task 9: Camera wrapper

**Files:**
- Create: `app/camera.py`

**Interfaces:**
- Consumes: `Settings` (Task 5).
- Produces: `class Picamera2Camera(settings)` with `set_exposure(exposure_us: int, gain: float)`, `lock_white_balance()`, `capture() -> np.ndarray` (full resolution, BGR uint8, usable directly by OpenCV), `close()`. The same four method names (`set_exposure`, `capture`, `close`) are what the scanner and runner call, so tests use a fake with the same methods.

`picamera2` exists only on the Pi, so this is verified by hand. The import is inside `__init__` so the module still imports on a PC.

- [ ] **Step 1: Write the implementation**

```python app/camera.py
import time


class Picamera2Camera:
    def __init__(self, settings):
        from picamera2 import Picamera2

        self._cam = Picamera2()
        # "RGB888" gives pixels in BGR order, which is what OpenCV expects
        config = self._cam.create_still_configuration(
            main={"size": (settings.width, settings.height), "format": "RGB888"}
        )
        self._cam.configure(config)
        self._cam.start()
        self.set_exposure(settings.exposure_us, settings.gain)

    def set_exposure(self, exposure_us, gain):
        self._cam.set_controls({"AeEnable": False, "ExposureTime": int(exposure_us), "AnalogueGain": float(gain)})

    def lock_white_balance(self):
        """Let auto white balance settle once under the scanner light, then freeze it."""
        self._cam.set_controls({"AwbEnable": True})
        time.sleep(2)
        gains = self._cam.capture_metadata()["ColourGains"]
        self._cam.set_controls({"AwbEnable": False, "ColourGains": gains})

    def capture(self):
        return self._cam.capture_array("main")

    def close(self):
        self._cam.stop()
        self._cam.close()
```

- [ ] **Step 2: Check it imports on a PC**

Run: `.venv/bin/python -c "import app.camera"`
Expected: no output

- [ ] **Step 3: Verify on the Pi with the HQ camera attached**

```bash
python3 - <<'EOF'
import cv2
from app.config import Settings
from app.camera import Picamera2Camera
cam = Picamera2Camera(Settings())
cam.lock_white_balance()
img = cam.capture()
print(img.shape, img.dtype)
cv2.imwrite("camera_check.png", img)
cam.close()
EOF
```
Expected: `(3040, 4056, 3) uint8` and a sensible-looking `camera_check.png` (colours not swapped).

- [ ] **Step 4: Commit**

```bash
git add app/camera.py && git commit -m "feat(app): picamera2 wrapper"
```

---

### Task 10: Scan loop

**Files:**
- Create: `app/scan.py`, `tests/fakes.py`
- Test: `tests/test_scan.py`

**Interfaces:**
- Consumes: `Settings` (Task 5); `detect_sprocket`, `shift_frame` (Task 7); `postprocess`, `wind_steps` (Task 8); a `controller` with `advance`, `wind`, `set_light` (Task 6) and a `camera` with `capture` (Task 9).
- Produces: `class ScanError(Exception)`; `next_frame_number(frames_dir: Path) -> int`; `class Scanner(controller, camera, settings, reel_dir, on_progress=None)` with attributes `state` (`idle|running|paused|done|error`), `frame_number: int`, `flagged: list[int]`, `target: tuple | None`, `error: str | None`, `preview: np.ndarray | None` (latest aligned frame, 640 px wide); methods `run(max_frames=None)` (blocking, never raises; records failures in `state`/`error`), `pause()`, `resume()`, `stop()`. Writes `reel_dir/frames/frame_%08d.png` and `reel_dir/scan.json`.
- Test fake: `FakeFilm(h=600, w=800, cy0=380)` with controller methods `advance`, `wind`, `set_light`, camera methods `capture`, `set_exposure`, `close`, and fields `pos`, `winds`, `light`, `blank_remaining`. Its real frame pitch is 170 steps but the app advances 164, so the film drifts and the scanner must nudge.

Loop per frame: capture, detect (retrying a few captures), nudge if the hole is far from the target row, otherwise save a shifted copy and advance. On the first detection the target is set to the hole's x and the image's mid-height, and it is stored in `scan.json` so a resumed scan keeps the same alignment.

- [ ] **Step 1: Write the fake and the failing tests**

```python tests/fakes.py
import numpy as np
from helpers import make_frame


class FakeFilm:
    """Fake camera and controller in one: the hole position follows how far the film was advanced."""

    PITCH = 170  # real frame pitch in steps; the app assumes 164, so the position drifts

    def __init__(self, h=600, w=800, cy0=380):
        self.h, self.w, self.cy0 = h, w, cy0
        self.pos = 0
        self.winds = []
        self.light = None
        self.blank_remaining = 0

    # controller
    def advance(self, steps, rate=None):
        self.pos += steps

    def wind(self, steps, rate=None):
        self.winds.append(steps)

    def set_light(self, percent):
        self.light = percent

    # camera
    def capture(self):
        if self.blank_remaining > 0:
            self.blank_remaining -= 1
            return np.zeros((self.h, self.w, 3), np.uint8)
        return make_frame(self.h, self.w, hole_cy=self.cy0 - (self.pos % self.PITCH))

    def set_exposure(self, exposure_us, gain):
        pass

    def close(self):
        pass
```

```python tests/test_scan.py
import json

import cv2
import pytest
from fakes import FakeFilm

from app.align import detect_sprocket
from app.config import Settings
from app.scan import Scanner, next_frame_number


def settings(**kw):
    return Settings(flip_vertical=False, **kw)


def scanner(film, tmp_path, s=None, **kw):
    return Scanner(film, film, s or settings(), tmp_path / "reel", **kw)


def test_saves_aligned_uncropped_frames(tmp_path):
    film = FakeFilm()
    sc = scanner(film, tmp_path)
    sc.run(max_frames=12)
    assert sc.state == "done"
    assert sc.frame_number == 12
    assert film.light == 0  # light is switched off afterwards
    frames = sorted((tmp_path / "reel" / "frames").glob("frame_*.png"))
    assert [p.name for p in frames] == ["frame_%08d.png" % i for i in range(12)]
    for p in frames:
        img = cv2.imread(str(p))
        assert img.shape[:2] == (600, 800)  # nothing cropped
        cx, cy = detect_sprocket(img, settings())
        assert cx == pytest.approx(sc.target[0], abs=1.5)
        assert cy == pytest.approx(sc.target[1], abs=1.5)  # hole sits on the target row


def test_winds_take_up_spool_after_enough_frames(tmp_path):
    film = FakeFilm()
    scanner(film, tmp_path).run(max_frames=12)
    assert len(film.winds) == 1 and film.winds[0] > 0


def test_blank_capture_is_flagged_and_scan_continues(tmp_path):
    film = FakeFilm()

    def hook(sc):
        if sc.frame_number == 2:
            film.blank_remaining = 3  # frame 2 and both retries are blank

    sc = scanner(film, tmp_path, settings(retries=2), on_progress=hook)
    sc.run(max_frames=6)
    assert sc.flagged == [2]
    assert sc.frame_number == 6
    assert json.loads((tmp_path / "reel" / "scan.json").read_text())["flagged"] == [2]


def test_lost_sprocket_stops_the_scan(tmp_path):
    film = FakeFilm()
    film.blank_remaining = 10 ** 6
    sc = scanner(film, tmp_path, settings(retries=0, max_consecutive_failures=3))
    sc.run(max_frames=50)
    assert sc.state == "error"
    assert "lost" in sc.error
    assert sc.frame_number == 2


def test_too_many_nudges_stops_the_scan(tmp_path):
    sc = scanner(FakeFilm(), tmp_path, settings(max_nudges=2))
    sc.run(max_frames=5)
    assert sc.state == "error"
    assert "nudges" in sc.error


def test_resume_continues_numbering_and_target(tmp_path):
    film = FakeFilm()
    first = scanner(film, tmp_path)
    first.run(max_frames=3)
    second = scanner(film, tmp_path)
    assert second.frame_number == 3
    assert second.target == pytest.approx(first.target)
    second.run(max_frames=3)
    assert next_frame_number(tmp_path / "reel" / "frames") == 6


def test_stop_before_run_does_nothing(tmp_path):
    sc = scanner(FakeFilm(), tmp_path)
    sc.stop()
    sc.run()
    assert sc.frame_number == 0
    assert sc.state == "done"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_scan.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.scan'`)

- [ ] **Step 3: Write the implementation**

```python app/scan.py
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import cv2

from .align import detect_sprocket, shift_frame
from .postprocess import postprocess
from .takeup import wind_steps

PENDING_WRITES = 4  # frames waiting to be written; bounds memory on the Pi
PREVIEW_WIDTH = 640


class ScanError(Exception):
    pass


def next_frame_number(frames_dir):
    numbers = [int(p.stem.split("_")[1]) for p in Path(frames_dir).glob("frame_????????.png")]
    return max(numbers) + 1 if numbers else 0


class Scanner:
    def __init__(self, controller, camera, settings, reel_dir, on_progress=None):
        self.controller = controller
        self.camera = camera
        self.settings = settings
        self.on_progress = on_progress
        self.reel_dir = Path(reel_dir)
        self.frames_dir = self.reel_dir / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.reel_dir / "scan.json"
        self.state = "idle"
        self.error = None
        self.preview = None
        self.frame_number = next_frame_number(self.frames_dir)
        self.flagged = []
        self.target = None  # where the hole centre is placed in every saved frame
        self._offset = (0.0, 0.0)
        self._stop = threading.Event()
        self._running = threading.Event()
        self._running.set()
        self._load_meta()

    # control -----------------------------------------------------------
    def pause(self):
        self._running.clear()
        self.state = "paused"

    def resume(self):
        self.state = "running"
        self._running.set()

    def stop(self):
        self._stop.set()
        self._running.set()

    # persistence -------------------------------------------------------
    def _load_meta(self):
        if self.meta_path.exists():
            meta = json.loads(self.meta_path.read_text())
            self.flagged = meta.get("flagged", [])
            if meta.get("target"):
                self.target = tuple(meta["target"])

    def _save_meta(self):
        self.meta_path.write_text(json.dumps({
            "settings": asdict(self.settings),
            "target": list(self.target) if self.target else None,
            "frames": self.frame_number,
            "flagged": self.flagged,
            "state": self.state,
        }, indent=2))

    # scan loop ---------------------------------------------------------
    def _grab(self):
        frame = self.camera.capture()
        return cv2.flip(frame, 0) if self.settings.flip_vertical else frame

    def _detect(self, frame):
        centre = detect_sprocket(frame, self.settings)
        for _ in range(self.settings.retries):
            if centre is not None:
                break
            frame = self._grab()
            centre = detect_sprocket(frame, self.settings)
        return frame, centre

    def _write(self, path, image):
        if not cv2.imwrite(str(path), image, [cv2.IMWRITE_PNG_COMPRESSION, self.settings.png_compression]):
            raise IOError("failed to write %s" % path)

    def run(self, max_frames=None):
        s = self.settings
        self.state = "running"
        self.error = None
        start = on_spool = self.frame_number
        to_wind = nudges = failures = 0
        pool = ThreadPoolExecutor(max_workers=3)
        slots = threading.BoundedSemaphore(PENDING_WRITES)
        futures = []
        try:
            self.controller.set_light(s.light_percent)
            while not self._stop.is_set():
                if max_frames is not None and self.frame_number - start >= max_frames:
                    break
                if not self._running.wait(0.1):
                    continue
                for f in [f for f in futures if f.done()]:
                    f.result()  # surface write errors early
                    futures.remove(f)

                frame, centre = self._detect(self._grab())
                h, w = frame.shape[:2]
                if centre is not None:
                    if self.target is None:
                        self.target = (centre[0], h / 2)
                    dy = self.target[1] - centre[1]
                    if abs(dy) > s.nudge_tolerance_frac * h:
                        nudges += 1
                        if nudges > s.max_nudges:
                            raise ScanError("too many nudges without finding the frame")
                        steps = s.nudge_forward_steps if centre[1] > self.target[1] else s.nudge_reverse_steps
                        self.controller.advance(steps, s.nudge_rate)
                        continue
                    self._offset = (self.target[0] - centre[0], dy)
                    failures = 0
                else:
                    failures += 1
                    if failures >= s.max_consecutive_failures:
                        raise ScanError("sprocket hole lost")
                    self.flagged.append(self.frame_number)  # keep the previous offset for this frame

                aligned = postprocess(shift_frame(frame, *self._offset), s)
                self.preview = cv2.resize(aligned, (PREVIEW_WIDTH, int(PREVIEW_WIDTH * h / w)))
                path = self.frames_dir / ("frame_%08d.png" % self.frame_number)
                slots.acquire()
                fut = pool.submit(self._write, path, aligned)
                fut.add_done_callback(lambda _f: slots.release())
                futures.append(fut)

                self.frame_number += 1
                to_wind += 1
                nudges = 0
                if to_wind >= s.frames_per_wind + 3:  # leave a little slack on the spool
                    self.controller.wind(wind_steps(on_spool, s.frames_per_wind, s), s.wind_rate)
                    on_spool += s.frames_per_wind
                    to_wind -= s.frames_per_wind
                self.controller.advance(s.steps_per_frame, s.advance_rate)
                if self.on_progress:
                    self.on_progress(self)
            self.state = "done"
        except Exception as e:
            self.error = "%s: %s" % (type(e).__name__, e)
            self.state = "error"
        finally:
            pool.shutdown(wait=True)
            for f in futures:
                if f.exception() and self.state != "error":
                    self.error = "%s: %s" % (type(f.exception()).__name__, f.exception())
                    self.state = "error"
            try:
                self.controller.set_light(0)
            except Exception:
                pass  # the controller may be what failed
            self._save_meta()
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_scan.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add app/scan.py tests/fakes.py tests/test_scan.py && git commit -m "feat(app): scan loop with alignment, nudging, flagging and resume"
```

---

### Task 11: MP4 builder

**Files:**
- Create: `app/video.py`
- Test: `tests/test_video.py`

**Interfaces:**
- Consumes: `Settings.fps` (Task 5).
- Produces: `ffmpeg_command(frames_dir: Path, out_path: Path, fps: int, start_number: int = 0) -> list[str]`; `build_mp4(reel_dir: Path, fps: int) -> Path` (runs ffmpeg on `reel_dir/frames`, writes `reel_dir/reel.mp4`, raises `subprocess.CalledProcessError` on failure).

- [ ] **Step 1: Write the failing test**

```python tests/test_video.py
from pathlib import Path

from app.video import ffmpeg_command


def test_command_reads_the_frame_sequence_and_writes_the_mp4():
    cmd = ffmpeg_command(Path("reel/frames"), Path("reel/reel.mp4"), 18)
    assert cmd[0] == "ffmpeg"
    assert cmd[cmd.index("-framerate") + 1] == "18"
    assert cmd[cmd.index("-i") + 1] == "reel/frames/frame_%08d.png"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[-1] == "reel/reel.mp4"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_video.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.video'`)

- [ ] **Step 3: Write the implementation**

```python app/video.py
import subprocess
from pathlib import Path


def ffmpeg_command(frames_dir, out_path, fps, start_number=0):
    return [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-start_number", str(start_number),
        "-i", str(Path(frames_dir) / "frame_%08d.png"),
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # yuv420p needs even dimensions
        "-c:v", "libx264", "-preset", "slower", "-crf", "15",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]


def build_mp4(reel_dir, fps):
    reel_dir = Path(reel_dir)
    out = reel_dir / "reel.mp4"
    subprocess.run(ffmpeg_command(reel_dir / "frames", out, fps), check=True, capture_output=True)
    return out
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_video.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add app/video.py tests/test_video.py && git commit -m "feat(app): ffmpeg MP4 builder"
```

---

### Task 12: Scan runner

**Files:**
- Create: `app/runner.py`
- Test: `tests/test_runner.py`

**Interfaces:**
- Consumes: `Scanner` (Task 10), `detect_sprocket` (Task 7), `build_mp4` (Task 11), `Settings` (Task 5), a controller and camera.
- Produces: `class RunnerError(Exception)` with `.status` (HTTP code: 400 bad input, 409 busy); `class ScanRunner(controller, camera, settings, build_video=build_mp4)` with `start(name: str, max_frames: int | None = None)`, `pause()`, `resume()`, `stop()`, `status() -> dict` (`state` of `idle|running|paused|encoding|done|error`, `name`, `frame`, `flagged`, `error`, `video`), `preview_jpeg() -> bytes`, `test_frame() -> dict` (`detected`, `x`, `y`), `set_light(percent)`, `set_exposure(exposure_us, gain)`. Reel names must match `[A-Za-z0-9_-]{1,64}` (it becomes a folder name). Calls that touch the hardware raise `RunnerError` (409) while a scan is running.

- [ ] **Step 1: Write the failing test**

```python tests/test_runner.py
import time

import pytest
from fakes import FakeFilm

from app.config import Settings
from app.runner import RunnerError, ScanRunner


def make_runner(tmp_path):
    film = FakeFilm()
    film.set_exposure = lambda us, gain: setattr(film, "exposure", (us, gain))
    settings = Settings(flip_vertical=False, output_dir=str(tmp_path))
    built = []
    return film, ScanRunner(film, film, settings, build_video=lambda d, fps: built.append((d, fps))), built


def wait_for(runner, states, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if runner.status()["state"] in states:
            return
        time.sleep(0.02)
    raise AssertionError("still %s" % runner.status())


def test_idle_status(tmp_path):
    _, runner, _ = make_runner(tmp_path)
    assert runner.status()["state"] == "idle"


@pytest.mark.parametrize("name", ["", "../x", "a b", "a/b", "x" * 65])
def test_bad_reel_names_are_rejected(tmp_path, name):
    _, runner, _ = make_runner(tmp_path)
    with pytest.raises(RunnerError) as e:
        runner.start(name)
    assert e.value.status == 400


def test_scan_runs_and_builds_video(tmp_path):
    _, runner, built = make_runner(tmp_path)
    runner.start("reel1", max_frames=3)
    wait_for(runner, {"done", "error"})
    st = runner.status()
    assert st["state"] == "done" and st["frame"] == 3 and st["name"] == "reel1"
    assert [d.name for d, _ in built] == ["reel1"]
    assert (tmp_path / "reel1" / "frames" / "frame_00000002.png").exists()


def test_second_start_while_running_is_refused_and_stop_works(tmp_path):
    _, runner, _ = make_runner(tmp_path)
    runner.start("reel1")
    with pytest.raises(RunnerError) as e:
        runner.start("reel2")
    assert e.value.status == 409
    with pytest.raises(RunnerError):
        runner.set_light(10)  # hardware is busy
    runner.stop()
    wait_for(runner, {"done"})


def test_preview_and_test_frame_when_idle(tmp_path):
    _, runner, _ = make_runner(tmp_path)
    assert runner.preview_jpeg()[:2] == b"\xff\xd8"
    result = runner.test_frame()
    assert result["detected"] is True
    assert result["y"] == pytest.approx(380, abs=2)


def test_light_and_exposure_pass_through(tmp_path):
    film, runner, _ = make_runner(tmp_path)
    runner.set_light(40)
    runner.set_exposure(3000, 1.5)
    assert film.light == 40
    assert film.exposure == (3000, 1.5)
    assert runner.settings.light_percent == 40
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_runner.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.runner'`)

- [ ] **Step 3: Write the implementation**

```python app/runner.py
import re
import threading
from pathlib import Path

import cv2

from .align import detect_sprocket
from .scan import PREVIEW_WIDTH, Scanner
from .video import build_mp4

NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class RunnerError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


class ScanRunner:
    def __init__(self, controller, camera, settings, build_video=build_mp4):
        self.controller = controller
        self.camera = camera
        self.settings = settings
        self._build_video = build_video
        self._scanner = None
        self._thread = None
        self._name = None
        self._video = None
        self._test_preview = None

    # helpers -----------------------------------------------------------
    def _busy(self):
        return self._thread is not None and self._thread.is_alive()

    def _require_idle(self):
        if self._busy():
            raise RunnerError("a scan is in progress")

    def _grab(self):
        frame = self.camera.capture()
        return cv2.flip(frame, 0) if self.settings.flip_vertical else frame

    @staticmethod
    def _jpeg(image):
        h, w = image.shape[:2]
        small = cv2.resize(image, (PREVIEW_WIDTH, int(PREVIEW_WIDTH * h / w)))
        return cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()

    # scan control ------------------------------------------------------
    def _run(self, max_frames):
        self._scanner.run(max_frames)
        if self._scanner.state == "done" and self._scanner.frame_number > 0:
            self._video = "encoding"
            try:
                self._build_video(Path(self.settings.output_dir) / self._name, self.settings.fps)
                self._video = "done"
            except Exception as e:  # ffmpeg missing or failed; frames are still saved
                self._video = "error: %s" % e

    def start(self, name, max_frames=None):
        if not NAME_RE.match(name):
            raise RunnerError("reel name must be 1-64 letters, digits, - or _", 400)
        self._require_idle()
        self._name = name
        self._video = None
        self._test_preview = None
        self._scanner = Scanner(self.controller, self.camera, self.settings, Path(self.settings.output_dir) / name)
        self._thread = threading.Thread(target=self._run, args=(max_frames,), daemon=True)
        self._thread.start()

    def pause(self):
        if self._busy():
            self._scanner.pause()

    def resume(self):
        if self._busy():
            self._scanner.resume()

    def stop(self):
        if self._busy():
            self._scanner.stop()

    def status(self):
        sc = self._scanner
        if sc is None:
            return {"state": "idle", "name": None, "frame": 0, "flagged": 0, "error": None, "video": None}
        state = "encoding" if self._video == "encoding" else sc.state
        return {"state": state, "name": self._name, "frame": sc.frame_number, "flagged": len(sc.flagged),
                "error": sc.error, "video": self._video}

    # hardware access (only while idle) ----------------------------------
    def preview_jpeg(self):
        if self._busy() and self._scanner.preview is not None:
            return self._jpeg(self._scanner.preview)
        if self._test_preview is not None:
            return self._test_preview
        self._require_idle()
        return self._jpeg(self._grab())

    def test_frame(self):
        self._require_idle()
        frame = self._grab()
        centre = detect_sprocket(frame, self.settings)
        shown = frame.copy()
        if centre is not None:
            cv2.circle(shown, (int(centre[0]), int(centre[1])), max(8, frame.shape[1] // 100), (0, 200, 0), -1)
        self._test_preview = self._jpeg(shown)
        if centre is None:
            return {"detected": False, "x": None, "y": None}
        return {"detected": True, "x": centre[0], "y": centre[1]}

    def set_light(self, percent):
        self._require_idle()
        self.controller.set_light(percent)
        self.settings.light_percent = percent

    def set_exposure(self, exposure_us, gain):
        self._require_idle()
        self.camera.set_exposure(exposure_us, gain)
        self.settings.exposure_us = exposure_us
        self.settings.gain = gain
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_runner.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add app/runner.py tests/test_runner.py && git commit -m "feat(app): scan runner with preview, test frame and hardware guards"
```

---

### Task 13: Web server and page

**Files:**
- Create: `app/server.py`, `app/static/index.html`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `ScanRunner`, `RunnerError` (Task 12).
- Produces: `create_app(runner) -> FastAPI` with routes `GET /` (page), `GET /api/status`, `POST /api/scan/start` (`{"name": str}`), `POST /api/scan/pause|resume|stop`, `GET /api/preview.jpg`, `POST /api/test-frame`, `POST /api/light` (`{"percent": 0-100}`), `POST /api/exposure` (`{"exposure_us": int > 0, "gain": 1.0-16.0}`). `RunnerError` becomes an HTTP error with its `.status`.

- [ ] **Step 1: Write the failing test**

```python tests/test_server.py
import time

from fakes import FakeFilm
from fastapi.testclient import TestClient

from app.config import Settings
from app.runner import ScanRunner
from app.server import create_app


def make_client(tmp_path):
    film = FakeFilm()
    film.set_exposure = lambda us, gain: None
    settings = Settings(flip_vertical=False, output_dir=str(tmp_path))
    runner = ScanRunner(film, film, settings, build_video=lambda d, fps: None)
    return TestClient(create_app(runner)), film


def test_page_and_idle_status(tmp_path):
    client, _ = make_client(tmp_path)
    assert "<title>" in client.get("/").text
    assert client.get("/api/status").json()["state"] == "idle"


def test_preview_and_test_frame(tmp_path):
    client, _ = make_client(tmp_path)
    r = client.get("/api/preview.jpg")
    assert r.headers["content-type"] == "image/jpeg"
    assert client.post("/api/test-frame").json()["detected"] is True


def test_light_and_exposure_validation(tmp_path):
    client, film = make_client(tmp_path)
    assert client.post("/api/light", json={"percent": 40}).status_code == 200
    assert film.light == 40
    assert client.post("/api/light", json={"percent": 101}).status_code == 422
    assert client.post("/api/exposure", json={"exposure_us": 0, "gain": 1.0}).status_code == 422
    assert client.post("/api/exposure", json={"exposure_us": 2000, "gain": 1.0}).status_code == 200


def test_start_stop_and_errors(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.post("/api/scan/start", json={"name": "../evil"}).status_code == 400
    assert client.post("/api/scan/start", json={"name": "reel1"}).status_code == 200
    assert client.post("/api/scan/start", json={"name": "reel2"}).status_code == 409
    assert client.post("/api/scan/pause").status_code == 200
    assert client.post("/api/scan/resume").status_code == 200
    assert client.post("/api/scan/stop").status_code == 200
    end = time.time() + 10
    while client.get("/api/status").json()["state"] not in ("done", "error") and time.time() < end:
        time.sleep(0.02)
    assert client.get("/api/status").json()["state"] == "done"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_server.py -q`
Expected: FAIL (`ModuleNotFoundError: No module named 'app.server'`)

- [ ] **Step 3: Write the server**

```python app/server.py
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .runner import RunnerError

STATIC = Path(__file__).parent / "static"


class StartRequest(BaseModel):
    name: str


class LightRequest(BaseModel):
    percent: int = Field(ge=0, le=100)


class ExposureRequest(BaseModel):
    exposure_us: int = Field(gt=0)
    gain: float = Field(ge=1.0, le=16.0)


def create_app(runner):
    app = FastAPI(title="Super 8 Scanner")

    def call(fn, *args):
        try:
            return fn(*args)
        except RunnerError as e:
            raise HTTPException(e.status, str(e))

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    def status():
        return runner.status()

    @app.post("/api/scan/start")
    def start(req: StartRequest):
        call(runner.start, req.name)
        return runner.status()

    @app.post("/api/scan/pause")
    def pause():
        runner.pause()
        return runner.status()

    @app.post("/api/scan/resume")
    def resume():
        runner.resume()
        return runner.status()

    @app.post("/api/scan/stop")
    def stop():
        runner.stop()
        return runner.status()

    @app.get("/api/preview.jpg")
    def preview():
        return Response(call(runner.preview_jpeg), media_type="image/jpeg")

    @app.post("/api/test-frame")
    def test_frame():
        return call(runner.test_frame)

    @app.post("/api/light")
    def light(req: LightRequest):
        call(runner.set_light, req.percent)
        return {"percent": req.percent}

    @app.post("/api/exposure")
    def exposure(req: ExposureRequest):
        call(runner.set_exposure, req.exposure_us, req.gain)
        return {"exposure_us": req.exposure_us, "gain": req.gain}

    return app
```

- [ ] **Step 4: Write the page**

```html app/static/index.html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Super 8 Scanner</title>
<style>
  :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
  body { margin: 0; padding: 16px; max-width: 760px; margin-inline: auto; }
  h1 { font-size: 1.3rem; }
  img { width: 100%; background: #111; border-radius: 6px; aspect-ratio: 4 / 3; object-fit: contain; }
  .row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 12px 0; }
  button { padding: 8px 14px; font-size: 1rem; }
  input[type=text], input[type=number] { padding: 6px; font-size: 1rem; width: 8em; }
  #status { font-variant-numeric: tabular-nums; padding: 8px; border-radius: 6px; background: rgba(128,128,128,.15); }
  .err { color: #c0392b; }
</style>
</head>
<body>
<h1>Super 8 Scanner</h1>
<div id="status">loading...</div>
<img id="preview" alt="preview">
<div class="row">
  <input id="name" type="text" placeholder="reel name" value="reel1" aria-label="Reel name">
  <button id="start">Start</button>
  <button id="pause">Pause</button>
  <button id="resume">Resume</button>
  <button id="stop">Stop</button>
  <button id="test">Test frame</button>
</div>
<div class="row">
  <label>Light <input id="light" type="range" min="0" max="100" value="100"> <span id="lightv">100</span>%</label>
</div>
<div class="row">
  <label>Exposure (&micro;s) <input id="exp" type="number" min="1" value="2000"></label>
  <label>Gain <input id="gain" type="number" min="1" max="16" step="0.1" value="1"></label>
  <button id="apply">Apply</button>
</div>
<div id="msg" class="err" role="status"></div>
<script>
const $ = id => document.getElementById(id);
async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "request failed (" + r.status + ")");
  return data;
}
async function act(fn) {
  try { $("msg").textContent = ""; await fn(); } catch (e) { $("msg").textContent = e.message; }
}
const post = (p, b) => act(() => api(p, b ?? {}));
$("start").onclick = () => post("/api/scan/start", {name: $("name").value});
$("pause").onclick = () => post("/api/scan/pause");
$("resume").onclick = () => post("/api/scan/resume");
$("stop").onclick = () => post("/api/scan/stop");
$("test").onclick = () => act(async () => {
  const r = await api("/api/test-frame", {});
  $("msg").textContent = r.detected ? "Sprocket hole found at " + Math.round(r.x) + ", " + Math.round(r.y) : "Sprocket hole not found";
  refreshPreview();
});
$("light").oninput = () => { $("lightv").textContent = $("light").value; };
$("light").onchange = () => post("/api/light", {percent: +$("light").value});
$("apply").onclick = () => post("/api/exposure", {exposure_us: +$("exp").value, gain: +$("gain").value});
function refreshPreview() { $("preview").src = "/api/preview.jpg?t=" + Date.now(); }
async function poll() {
  try {
    const s = await api("/api/status");
    $("status").textContent = s.state + (s.name ? " | " + s.name : "") + " | frames " + s.frame + " | flagged " + s.flagged +
      (s.video ? " | video " + s.video : "") + (s.error ? " | " + s.error : "");
    $("status").className = s.error ? "err" : "";
    if (s.state === "running" || s.state === "paused") refreshPreview();
  } catch (e) { $("status").textContent = "cannot reach scanner"; }
}
refreshPreview();
setInterval(poll, 1500);
poll();
</script>
</body>
</html>
```

- [ ] **Step 5: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_server.py -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add app/server.py app/static/index.html tests/test_server.py && git commit -m "feat(app): FastAPI server and web page"
```

---

### Task 14: Entrypoint, README and on-hardware check

**Files:**
- Create: `app/__main__.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above. Produces: `python -m app [--config scanner.json] [--port 8000]` serving the UI on all interfaces.

- [ ] **Step 1: Write the entrypoint**

```python app/__main__.py
import argparse

import uvicorn

from .camera import Picamera2Camera
from .config import Settings
from .controller import Controller
from .runner import ScanRunner
from .server import create_app


def main():
    parser = argparse.ArgumentParser(description="Super 8 scanner web app")
    parser.add_argument("--config", default="scanner.json")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    settings = Settings.load(args.config)
    controller = Controller.open(settings)
    controller.set_light(settings.light_percent)
    camera = Picamera2Camera(settings)
    camera.lock_white_balance()  # with the scanner light on and empty gate
    runner = ScanRunner(controller, camera, settings)
    uvicorn.run(create_app(runner), host="0.0.0.0", port=args.port)  # LAN only, no auth in v1


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add a README section**

In `README.md`, insert directly after the first paragraph (the one ending "pull requests are very welcome!") this block, and add `(legacy)` to the existing "Setup" and "Scanning Process" headings:

```markdown
## New web app (work in progress)

The scripts in `legacy/` are the original Marlin-based workflow, kept for reference. The new version is `app/` (Pi web UI) plus `firmware/` (RP2040 controller).

On Raspberry Pi OS (Bookworm):

    sudo apt install -y python3-picamera2 python3-opencv python3-numpy ffmpeg
    python3 -m venv --system-site-packages .venv && .venv/bin/pip install -r requirements.txt
    .venv/bin/python -m app --config scanner.json

Open `http://<pi-hostname>.local:8000`. There is no login, so only run it on a network you trust.
Each reel is saved to `scans/<name>/frames/` as aligned, uncropped PNGs, with `reel.mp4` and `scan.json`.
Hardware numbers (steps per frame, motor rates, sprocket threshold) live in `scanner.json`; see `app/config.py` for every setting and its default.
```

- [ ] **Step 3: Run the full test suite**

Run: `.venv/bin/pytest -q`
Expected: all tests pass

- [ ] **Step 4: Check on the real hardware (manual)**

1. Flash the Pico (Task 4), connect it to the Pi, start the app, open the page on a phone or laptop.
2. Load a reel with the gate lit. Move the light slider; the light follows. Click "Test frame": "Sprocket hole found at ...". If it is not found, change `sprocket_threshold` or `sprocket_strip_frac` in `scanner.json` and restart.
3. Calibrate `steps_per_frame`: scan 20 frames and watch for nudges. Adjust until nudges are rare. If the film nudges the wrong way, set `flip_vertical` the other way.
4. Scan a short reel (about 50 frames). Check that frames are full size, the sprocket hole sits at the same position in every frame, nothing is cropped, and `reel.mp4` plays at 18 fps.
5. Check that denoise is not applied by default (frames keep their grain).

- [ ] **Step 5: Commit**

```bash
git add app/__main__.py README.md && git commit -m "feat(app): entrypoint and README for the new app"
```

---

## Self-Review

**Spec coverage**
- Aligned, uncropped frames; MP4; `scan.json`: Tasks 7, 10, 11, 12.
- Denoise/resize off by default and opt-in: Tasks 5, 8.
- Web UI over LAN (preview, light, exposure, start/stop/pause, test frame, progress): Tasks 12, 13.
- RP2040 controller with protocol, TMC2209 steppers, LED PWM, sensor input reserved: Tasks 2 to 4 (sensor pin reserved only; no use in v1).
- `picamera2` HQ camera, fixed exposure and locked white balance: Task 9, `__main__`.
- Error handling (retry, flag, continue; controller failure pauses with an error): Task 10 (a controller error sets `state="error"` and stops; the UI shows it).
- Repo reorganisation with `legacy/`: Task 1.
- Enclosure, PCB and lighting hardware: out of this plan by design (separate plans).

**Additions beyond the spec text** (needed by the real scan loop, taken from the legacy script): the nudge step that moves the film until the hole is near the target row, spool take-up winding, and stopping after repeated sprocket failures. The spec should be updated to mention these.

**Type consistency:** `Controller.advance/wind(steps, rate=None)`, `set_light(percent)`, `Scanner(controller, camera, settings, reel_dir, on_progress)`, `ScanRunner.start(name, max_frames=None)`, `detect_sprocket(image, settings)` and `shift_frame(image, dx, dy)` are used with the same names and arguments in every task that calls them.
