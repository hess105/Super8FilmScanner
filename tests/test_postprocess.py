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
