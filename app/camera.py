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
