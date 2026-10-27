import re
import threading
from pathlib import Path

import cv2

from .align import detect_sprocket
from .scan import PREVIEW_WIDTH, Scanner
from .video import build_mp4

NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


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
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            raise RunnerError("reel name must be 1-64 letters, digits, - or _", 400)
        with self._lock:
            self._require_idle()
            self._name = name
            self._video = None
            self._test_preview = None
            self._scanner = Scanner(self.controller, self.camera, self.settings, Path(self.settings.output_dir) / name)
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

    def status(self):
        sc = self._scanner
        if sc is None:
            return {"state": "idle", "name": None, "frame": 0, "flagged": 0, "error": None, "video": None}
        # Scanner sets "done" before its writes drain and the video is built; never report done while the thread lives
        state = "encoding" if self._busy() and sc.state == "done" else sc.state
        return {"state": state, "name": self._name, "frame": sc.frame_number, "flagged": len(sc.flagged),
                "error": sc.error, "video": self._video}

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
            return {"detected": False, "x": None, "y": None}
        return {"detected": True, "x": centre[0], "y": centre[1]}

    def set_light(self, percent):
        with self._lock:
            self._require_idle()
            self.controller.set_light(percent)
            self.settings.light_percent = percent

    def set_exposure(self, exposure_us, gain):
        with self._lock:
            self._require_idle()
            self.camera.set_exposure(exposure_us, gain)
            self.settings.exposure_us = exposure_us
            self.settings.gain = gain
