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
