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
