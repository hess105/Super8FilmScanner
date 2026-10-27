import re
import shutil
import threading
import time
from collections import deque
from pathlib import Path

import cv2

from .align import detect_sprocket
from .console import CommandLog
from .controller import ControllerError
from .scan import PREVIEW_WIDTH, Scanner

NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
RATE_WINDOW_S = 30


class RunnerError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


class ScanRunner:
    def __init__(self, controller, camera, settings, log=None):
        self.controller = controller
        self.camera = camera
        self.settings = settings
        self.log = log or CommandLog()
        self._scanner = None
        self._started = self._ended = None  # monotonic times of the current scan
        self._frame_times = deque()  # monotonic time of each recent frame, for rate_fps
        self._thread = None
        self._name = None
        self._test_preview = None
        self._lock = threading.Lock()  # idle check + action must be atomic

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
    def _event(self, text):
        self.log.add("event", text)

    def _on_frame(self, scanner):
        now = time.monotonic()
        self._frame_times.append(now)
        while self._frame_times and now - self._frame_times[0] > RATE_WINDOW_S:
            self._frame_times.popleft()

    def _run(self, max_frames):
        try:
            self._scanner.run(max_frames)
        finally:
            self._ended = time.monotonic()

    def start(self, name, max_frames=None):
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            raise RunnerError("reel name must be 1-64 letters, digits, - or _", 400)
        with self._lock:
            self._require_idle()
            self._name = name
            self._test_preview = None
            self._frame_times.clear()
            self._started, self._ended = time.monotonic(), None
            self._scanner = Scanner(self.controller, self.camera, self.settings, Path(self.settings.output_dir) / name,
                                    on_progress=self._on_frame, on_event=self._event)
            self._thread = threading.Thread(target=self._run, args=(max_frames,), daemon=True)
            self._thread.start()

    def pause(self):
        if self._busy() and self._scanner.state in ("running", "paused"):
            self._scanner.pause()

    def resume(self):
        if self._busy() and self._scanner.state in ("running", "paused"):
            self._scanner.resume()

    def stop(self):
        if self._busy():
            self._scanner.stop()

    def shutdown(self, timeout=60):
        """Stop any scan and wait for it to finish writing frames and scan.json."""
        self.stop()
        if self._thread is not None:
            self._thread.join(timeout)

    def _disk_free_gb(self):
        path = Path(self.settings.output_dir).resolve()
        while not path.exists():  # the output folder is made by the first scan
            path = path.parent
        return round(shutil.disk_usage(path).free / 1e9, 1)

    def _rate_fps(self):
        times = list(self._frame_times)
        if not self._busy() or self._scanner.state != "running" or len(times) < 2:
            return 0
        return round((len(times) - 1) / max(time.monotonic() - times[0], 1e-3), 2)

    def status(self):
        sc = self._scanner
        extra = {"disk_free_gb": self._disk_free_gb(), "flagged_frames": [], "elapsed_s": 0, "rate_fps": 0,
                 "target_frac": None}
        if sc is None:
            return {"state": "idle", "name": None, "frame": 0, "flagged": 0, "error": None, **extra}
        # Scanner sets "done" before its writes drain, the light goes off and scan.json is saved; never report done while the thread lives
        state = "finishing" if self._busy() and sc.state == "done" else sc.state
        if sc.target and sc.frame_size:
            extra["target_frac"] = [sc.target[0] / sc.frame_size[0], sc.target[1] / sc.frame_size[1]]
        extra["flagged_frames"] = sc.flagged[-50:]
        extra["elapsed_s"] = (self._ended or time.monotonic()) - self._started
        extra["rate_fps"] = self._rate_fps()
        return {"state": state, "name": self._name, "frame": sc.frame_number, "flagged": len(sc.flagged),
                "error": sc.error, **extra}

    # hardware access (only while idle) ----------------------------------
    def preview_jpeg(self):
        if self._busy() and self._scanner.preview is not None:
            return self._jpeg(self._scanner.preview)
        if self._test_preview is not None:
            return self._test_preview
        with self._lock:
            self._require_idle()
            return self._jpeg(self._grab())

    def test_frame(self):
        with self._lock:
            return self._test_frame()

    def _test_frame(self):
        self._require_idle()
        self.controller.set_light(self.settings.light_percent)  # a finished scan leaves it off
        frame = self._grab()
        centre = detect_sprocket(frame, self.settings)
        shown = frame.copy()
        if centre is not None:
            cv2.circle(shown, (int(centre[0]), int(centre[1])), max(8, frame.shape[1] // 100), (0, 200, 0), -1)
        self._test_preview = self._jpeg(shown)
        if centre is None:
            self._event("test frame: hole not found")
            return {"detected": False, "x": None, "y": None}
        self._event("test frame: hole at %d, %d" % (round(centre[0]), round(centre[1])))
        return {"detected": True, "x": centre[0], "y": centre[1]}

    def set_light(self, percent):
        with self._lock:
            self._require_idle()
            self.controller.set_light(percent)
            self.settings.light_percent = percent
            self._event("light set to %d%%" % percent)

    def set_exposure(self, exposure_us, gain):
        with self._lock:
            self._require_idle()
            self.camera.set_exposure(exposure_us, gain)
            self.settings.exposure_us = exposure_us
            self.settings.gain = gain
            self._event("exposure %d us, gain %.1f" % (exposure_us, gain))

    # terminal ----------------------------------------------------------
    def log_since(self, last_id):
        last = self.log.last_id  # read first: an entry added meanwhile comes with the next call, never skipped
        return {"entries": [e for e in self.log.since(last_id) if e["id"] <= last], "last_id": last}

    def console(self, command):
        with self._lock:
            self._require_idle()
            try:
                return {"reply": self.controller.command(command)}
            except ValueError as e:
                raise RunnerError(str(e), 400)
            except ControllerError as e:
                raise RunnerError(str(e), 502)
