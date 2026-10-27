from app.config import Settings
from app.takeup import wind_steps


def test_empty_spool_first_eight_frames():
    # 8 frames * 4.01 mm on a 32 mm core = 114.9 degrees of 3200 steps/rev
    assert wind_steps(0, 8, Settings()) == 1021


def test_fuller_spool_needs_fewer_steps():
    s = Settings()
    assert wind_steps(3000, 8, s) < wind_steps(0, 8, s)
