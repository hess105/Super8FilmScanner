import json
import os
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
    def __init__(self, controller, camera, settings, reel_dir, on_progress=None, on_event=None):
        self.controller = controller
        self.camera = camera
        self.settings = settings
        self.on_progress = on_progress
        self.on_event = on_event or (lambda text: None)
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
        self.frame_size = None  # (width, height) of captured frames, once one is seen
        self._offset = (0.0, 0.0)
        self._stop = threading.Event()
        self._running = threading.Event()
        self._running.set()
        self._load_meta()

    # control -----------------------------------------------------------
    def pause(self):
        self._running.clear()
        self.state = "paused"
        self.on_event("paused")

    def resume(self):
        self.state = "running"
        self._running.set()
        self.on_event("resumed")

    def stop(self):
        self._stop.set()
        self._running.set()
        self.on_event("stop requested")

    # persistence -------------------------------------------------------
    def _load_meta(self):
        if self.meta_path.exists():
            try:
                meta = json.loads(self.meta_path.read_text())
                flagged = list(meta.get("flagged", []))
                target = tuple(meta["target"]) if meta.get("target") else None
            except (ValueError, TypeError, AttributeError, KeyError, OSError):
                return  # corrupt scan.json: start with defaults
            self.flagged = flagged
            self.target = target

    def _save_meta(self):
        tmp = self.meta_path.with_name(self.meta_path.name + ".tmp")
        tmp.write_text(json.dumps({
            "settings": asdict(self.settings),
            "target": list(self.target) if self.target else None,
            "frames": self.frame_number,
            "flagged": self.flagged,
            "state": self.state,
        }, indent=2))
        os.replace(tmp, self.meta_path)  # atomic: never leaves a half-written scan.json

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
        tmp = path.with_name(path.stem + ".tmp.png")  # not matched by next_frame_number
        if not cv2.imwrite(str(tmp), image, [cv2.IMWRITE_PNG_COMPRESSION, self.settings.png_compression]):
            raise IOError("failed to write %s" % path)
        os.replace(tmp, path)  # a hard kill never leaves a truncated frame

    def run(self, max_frames=None):
        s = self.settings
        self.state = "running" if self._running.is_set() else "paused"  # a pause() before run() sticks
        self.error = None
        start = on_spool = self.frame_number
        to_wind = nudges = failures = 0
        pool = ThreadPoolExecutor(max_workers=3)
        slots = threading.BoundedSemaphore(PENDING_WRITES)
        futures = {}  # write future -> frame number
        write_errors = []

        def reap(wait=False):
            for f, n in list(futures.items()):
                if wait or f.done():
                    del futures[f]
                    if f.exception():
                        if n not in self.flagged:
                            self.flagged.append(n)
                        write_errors.append("frame %d write failed: %s: %s" % (n, type(f.exception()).__name__, f.exception()))

        self.on_event("scan started at frame %d" % start)
        try:
            self.controller.set_light(s.light_percent)
            while not self._stop.is_set():
                if max_frames is not None and self.frame_number - start >= max_frames:
                    break
                if not self._running.wait(0.1) or self._stop.is_set():
                    continue
                reap()
                if write_errors:
                    raise ScanError("frame write failed")

                frame, centre = self._detect(self._grab())
                h, w = frame.shape[:2]
                self.frame_size = (w, h)
                if centre is not None:
                    if self.target is None:
                        self.target = (centre[0], h / 2)
                        self._save_meta()
                        self.on_event("target set at %d, %d" % self.target)
                    dy = self.target[1] - centre[1]
                    if abs(dy) > s.nudge_tolerance_frac * h:
                        nudges += 1
                        if nudges > s.max_nudges:
                            raise ScanError("too many nudges without finding the frame")
                        steps = s.nudge_forward_steps if centre[1] > self.target[1] else s.nudge_reverse_steps
                        self.controller.advance(steps, s.nudge_rate)
                        self.on_event("nudge %s %d steps (hole %d px %s target)" % (
                            "forward" if steps > 0 else "back", abs(steps), abs(dy), "below" if dy < 0 else "above"))
                        continue
                    self._offset = (self.target[0] - centre[0], dy)
                    failures = 0
                else:
                    failures += 1
                    if failures >= s.max_consecutive_failures:
                        raise ScanError("sprocket hole lost")
                    self.flagged.append(self.frame_number)  # keep the previous offset for this frame
                    self._save_meta()
                    self.on_event("frame %d flagged: sprocket hole not found" % self.frame_number)

                aligned = postprocess(shift_frame(frame, *self._offset), s)
                self.preview = cv2.resize(aligned, (PREVIEW_WIDTH, int(PREVIEW_WIDTH * h / w)))
                path = self.frames_dir / ("frame_%08d.png" % self.frame_number)
                slots.acquire()
                fut = pool.submit(self._write, path, aligned)
                fut.add_done_callback(lambda _f: slots.release())
                futures[fut] = self.frame_number

                self.frame_number += 1
                to_wind += 1
                nudges = 0
                if to_wind >= s.frames_per_wind + 3:  # leave a little slack on the spool
                    steps = wind_steps(on_spool, s.frames_per_wind, s)
                    self.controller.wind(steps, s.wind_rate)
                    self.on_event("wind %d steps" % steps)
                    on_spool += s.frames_per_wind
                    to_wind -= s.frames_per_wind
                    self._save_meta()
                self.controller.advance(s.steps_per_frame, s.advance_rate)
                if self.on_progress:
                    self.on_progress(self)
            self.state = "done"
        except Exception as e:
            self.error = "%s: %s" % (type(e).__name__, e)
            self.state = "error"
        finally:
            pool.shutdown(wait=True)
            reap(wait=True)
            if write_errors:
                self.error = "; ".join(([self.error] if self.error else []) + write_errors)
                self.state = "error"
            try:
                self.controller.set_light(0)
            except Exception:
                pass  # the controller may be what failed
            try:
                self._save_meta()
            except Exception as e:
                self.error = "; ".join(([self.error] if self.error else []) + ["scan.json not saved: %s: %s" % (type(e).__name__, e)])
                self.state = "error"
            if self.state == "error":
                self.on_event("error: %s" % self.error)
            else:
                self.on_event("done: %d frames, %d flagged" % (self.frame_number, len(self.flagged)))
