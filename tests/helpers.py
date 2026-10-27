import numpy as np


def make_frame(h=600, w=800, hole_cx=74, hole_cy=300, hole_w=100, hole_h=130, picture=120):
    """BGR test frame: dark film edge, bright sprocket hole on the left, grey picture."""
    img = np.zeros((h, w, 3), np.uint8)
    img[:, int(w * 0.18):] = picture
    x0, y0 = hole_cx - hole_w // 2, hole_cy - hole_h // 2
    img[max(y0, 0):y0 + hole_h, max(x0, 0):x0 + hole_w] = 255
    return img
