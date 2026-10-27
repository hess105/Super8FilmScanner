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
