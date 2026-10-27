import json
import threading
import time

import pytest
from fakes import FakeFilm

from app.config import Settings
from app.scan import Scanner
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


@pytest.mark.parametrize("name", ["", "../x", "a b", "a/b", "x" * 65, "a\n", None])
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


class GatedFilm(FakeFilm):
    """set_light (the first thing a scan does) blocks until the gate opens, so the scan stays busy with no preview."""

    def __init__(self):
        super().__init__()
        self.gate = threading.Event()

    def set_light(self, percent):
        if percent != 0 and threading.current_thread().name != "MainThread":
            self.gate.wait(10)
        super().set_light(percent)


def gated_runner(tmp_path, **kw):
    film = GatedFilm()
    settings = Settings(flip_vertical=False, output_dir=str(tmp_path))
    return film, ScanRunner(film, film, settings, **kw)


@pytest.mark.parametrize("call", [
    lambda r: r.preview_jpeg(),
    lambda r: r.test_frame(),
    lambda r: r.set_light(10),
    lambda r: r.set_exposure(1000, 1.0),
])
def test_hardware_calls_are_busy_while_scanning(tmp_path, call):
    film, runner = gated_runner(tmp_path, build_video=lambda d, f: None)
    runner.start("reel1")
    try:
        with pytest.raises(RunnerError) as e:
            call(runner)
        assert e.value.status == 409
    finally:
        film.gate.set()
        runner.stop()
        wait_for(runner, {"done"})


def test_concurrent_starts_only_one_wins(tmp_path):
    film, runner = gated_runner(tmp_path, build_video=lambda d, f: None)
    barrier = threading.Barrier(2)
    results = []

    def go(name):
        barrier.wait()
        try:
            runner.start(name)
            results.append("ok")
        except RunnerError as e:
            results.append(e.status)

    threads = [threading.Thread(target=go, args=(n,)) for n in ("a", "b")]
    [t.start() for t in threads]
    [t.join() for t in threads]
    film.gate.set()
    runner.stop()
    wait_for(runner, {"done"})
    assert sorted(results, key=str) == [409, "ok"]


def test_failing_video_build_is_reported_and_state_is_done(tmp_path):
    def boom(d, fps):
        raise RuntimeError("no ffmpeg")

    film, runner = gated_runner(tmp_path, build_video=boom)
    film.gate.set()
    runner.start("reel1", max_frames=2)
    wait_for(runner, {"done", "error"})
    runner._thread.join(5)
    st = runner.status()
    assert st["state"] == "done" and st["video"].startswith("error:") and "no ffmpeg" in st["video"]
    assert not runner._thread.is_alive()


def test_encoding_state_and_never_done_while_thread_alive(tmp_path):
    release = threading.Event()
    film, runner = gated_runner(tmp_path, build_video=lambda d, f: release.wait(10))
    film.gate.set()
    runner.start("reel1", max_frames=2)
    wait_for(runner, {"encoding"})
    for _ in range(50):
        assert runner.status()["state"] == "encoding"
        time.sleep(0.002)
    release.set()
    seen = []
    end = time.time() + 10
    while time.time() < end:
        st = runner.status()["state"]
        seen.append(st)
        if st == "done":
            assert not runner._thread.is_alive()
            break
        time.sleep(0.001)
    assert seen[-1] == "done"
    assert runner.status()["video"] == "done"


def test_pause_then_resume_completes_scan(tmp_path):
    film, runner = gated_runner(tmp_path, build_video=lambda d, f: None)
    runner.start("reel1", max_frames=3)
    wait_for(runner, {"running"})
    runner.pause()
    film.gate.set()
    wait_for(runner, {"paused"})
    time.sleep(0.2)
    assert runner.status()["state"] == "paused" and runner.status()["frame"] == 0
    runner.resume()
    wait_for(runner, {"done"})
    assert runner.status()["frame"] == 3


def test_pause_and_resume_ignored_when_not_scanning(tmp_path):
    _, runner, _ = make_runner(tmp_path)
    runner.pause()
    runner.resume()
    assert runner.status()["state"] == "idle"
    runner.start("reel1", max_frames=1)
    wait_for(runner, {"done"})
    runner._thread.join(5)
    runner.pause()
    assert runner.status()["state"] == "done"


def test_scanner_pause_before_run_sticks(tmp_path):
    film = FakeFilm()
    scanner = Scanner(film, film, Settings(flip_vertical=False, output_dir=str(tmp_path)), tmp_path / "r")
    scanner.pause()
    t = threading.Thread(target=scanner.run, args=(1,), daemon=True)
    t.start()
    time.sleep(0.3)
    assert scanner.state == "paused" and scanner.frame_number == 0
    scanner.resume()
    t.join(10)
    assert scanner.state == "done" and scanner.frame_number == 1


def test_preview_after_test_frame_returns_cached_test_preview(tmp_path):
    _, runner, _ = make_runner(tmp_path)
    runner.test_frame()
    cached = runner._test_preview
    assert cached is not None and runner.preview_jpeg() is cached


def test_shutdown_stops_scan_and_saves_state(tmp_path):
    _, runner, _ = make_runner(tmp_path)
    runner.shutdown()  # no scan: no error
    runner.start("reel1")
    wait_for(runner, {"running"})
    runner.shutdown()
    assert not runner._thread.is_alive()
    meta = json.loads((tmp_path / "reel1" / "scan.json").read_text())
    assert meta["state"] == "done"


def test_test_frame_after_scan_turns_light_back_on(tmp_path):
    film, runner, _ = make_runner(tmp_path)
    runner.start("reel1", max_frames=2)
    wait_for(runner, {"done"})
    assert film.light == 0
    assert runner.test_frame()["detected"] is True
    assert film.light == runner.settings.light_percent
