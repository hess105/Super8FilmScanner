import time

import pytest
from fakes import FakeFilm

from app.config import Settings
from app.runner import RunnerError, ScanRunner


def make_runner(tmp_path):
    film = FakeFilm()
    film.set_exposure = lambda us, gain: setattr(film, "exposure", (us, gain))
    settings = Settings(flip_vertical=False, output_dir=str(tmp_path))
    built = []
    return film, ScanRunner(film, film, settings, build_video=lambda d, fps: built.append((d, fps))), built


def wait_for(runner, states, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if runner.status()["state"] in states:
            return
        time.sleep(0.02)
    raise AssertionError("still %s" % runner.status())


def test_idle_status(tmp_path):
    _, runner, _ = make_runner(tmp_path)
    assert runner.status()["state"] == "idle"


@pytest.mark.parametrize("name", ["", "../x", "a b", "a/b", "x" * 65])
def test_bad_reel_names_are_rejected(tmp_path, name):
    _, runner, _ = make_runner(tmp_path)
    with pytest.raises(RunnerError) as e:
        runner.start(name)
    assert e.value.status == 400


def test_scan_runs_and_builds_video(tmp_path):
    _, runner, built = make_runner(tmp_path)
    runner.start("reel1", max_frames=3)
    wait_for(runner, {"done", "error"})
    st = runner.status()
    assert st["state"] == "done" and st["frame"] == 3 and st["name"] == "reel1"
    assert [d.name for d, _ in built] == ["reel1"]
    assert (tmp_path / "reel1" / "frames" / "frame_00000002.png").exists()


def test_second_start_while_running_is_refused_and_stop_works(tmp_path):
    _, runner, _ = make_runner(tmp_path)
    runner.start("reel1")
    with pytest.raises(RunnerError) as e:
        runner.start("reel2")
    assert e.value.status == 409
    with pytest.raises(RunnerError):
        runner.set_light(10)  # hardware is busy
    runner.stop()
    wait_for(runner, {"done"})


def test_preview_and_test_frame_when_idle(tmp_path):
    _, runner, _ = make_runner(tmp_path)
    assert runner.preview_jpeg()[:2] == b"\xff\xd8"
    result = runner.test_frame()
    assert result["detected"] is True
    assert result["y"] == pytest.approx(380, abs=2)


def test_light_and_exposure_pass_through(tmp_path):
    film, runner, _ = make_runner(tmp_path)
    runner.set_light(40)
    runner.set_exposure(3000, 1.5)
    assert film.light == 40
    assert film.exposure == (3000, 1.5)
    assert runner.settings.light_percent == 40
