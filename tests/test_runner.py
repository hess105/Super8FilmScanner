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
    settings = Settings(flip_vertical=False, light_control=True, output_dir=str(tmp_path))
    return film, ScanRunner(film, film, settings)


def wait_for(runner, states, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if runner.status()["state"] in states:
            return
        time.sleep(0.02)
    raise AssertionError("still %s" % runner.status())


def test_idle_status(tmp_path):
    _, runner = make_runner(tmp_path)
    assert runner.status()["state"] == "idle"


def test_status_has_no_video_key(tmp_path):
    _, runner = make_runner(tmp_path)
    assert "video" not in runner.status()
    runner.start("reel1", max_frames=1)
    wait_for(runner, {"done"})
    assert "video" not in runner.status()


@pytest.mark.parametrize("name", ["", "../x", "a b", "a/b", "x" * 65, "a\n", None])
def test_bad_reel_names_are_rejected(tmp_path, name):
    _, runner = make_runner(tmp_path)
    with pytest.raises(RunnerError) as e:
        runner.start(name)
    assert e.value.status == 400


def test_scan_runs_and_saves_frames(tmp_path):
    _, runner = make_runner(tmp_path)
    runner.start("reel1", max_frames=3)
    wait_for(runner, {"done", "error"})
    st = runner.status()
    assert st["state"] == "done" and st["frame"] == 3 and st["name"] == "reel1"
    assert (tmp_path / "reel1" / "frames" / "frame_00000002.png").exists()


def test_second_start_while_running_is_refused_and_stop_works(tmp_path):
    _, runner = make_runner(tmp_path)
    runner.start("reel1")
    with pytest.raises(RunnerError) as e:
        runner.start("reel2")
    assert e.value.status == 409
    with pytest.raises(RunnerError):
        runner.set_light(10)  # hardware is busy
    runner.stop()
    wait_for(runner, {"done"})


def test_preview_and_test_frame_when_idle(tmp_path):
    _, runner = make_runner(tmp_path)
    assert runner.preview_jpeg()[:2] == b"\xff\xd8"
    result = runner.test_frame()
    assert result["detected"] is True
    assert result["y"] == pytest.approx(380, abs=2)


def test_light_and_exposure_pass_through(tmp_path):
    film, runner = make_runner(tmp_path)
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
    settings = Settings(flip_vertical=False, light_control=True, output_dir=str(tmp_path))
    return film, ScanRunner(film, film, settings, **kw)


@pytest.mark.parametrize("call", [
    lambda r: r.preview_jpeg(),
    lambda r: r.test_frame(),
    lambda r: r.set_light(10),
    lambda r: r.set_exposure(1000, 1.0),
])
def test_hardware_calls_are_busy_while_scanning(tmp_path, call):
    film, runner = gated_runner(tmp_path)
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
    film, runner = gated_runner(tmp_path)
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


class SlowOffFilm(FakeFilm):
    """The scan thread's final set_light(0) blocks: the window where Scanner says done but the thread still lives."""

    def __init__(self):
        super().__init__()
        self.release = threading.Event()

    def set_light(self, percent):
        if percent == 0 and threading.current_thread().name != "MainThread":
            self.release.wait(10)
        super().set_light(percent)


def test_finishing_state_and_never_done_while_thread_alive(tmp_path):
    film = SlowOffFilm()
    runner = ScanRunner(film, film, Settings(flip_vertical=False, light_control=True, output_dir=str(tmp_path)))
    runner.start("reel1", max_frames=2)
    wait_for(runner, {"finishing"})
    for _ in range(50):
        assert runner.status()["state"] == "finishing"
        time.sleep(0.002)
    film.release.set()
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


def test_pause_then_resume_completes_scan(tmp_path):
    film, runner = gated_runner(tmp_path)
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
    _, runner = make_runner(tmp_path)
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
    scanner = Scanner(film, film, Settings(flip_vertical=False, light_control=True, output_dir=str(tmp_path)), tmp_path / "r")
    scanner.pause()
    t = threading.Thread(target=scanner.run, args=(1,), daemon=True)
    t.start()
    time.sleep(0.3)
    assert scanner.state == "paused" and scanner.frame_number == 0
    scanner.resume()
    t.join(10)
    assert scanner.state == "done" and scanner.frame_number == 1


def test_preview_after_test_frame_returns_cached_test_preview(tmp_path):
    _, runner = make_runner(tmp_path)
    runner.test_frame()
    cached = runner._test_preview
    assert cached is not None and runner.preview_jpeg() is cached


def test_shutdown_stops_scan_and_saves_state(tmp_path):
    _, runner = make_runner(tmp_path)
    runner.shutdown()  # no scan: no error
    runner.start("reel1")
    wait_for(runner, {"running"})
    runner.shutdown()
    assert not runner._thread.is_alive()
    meta = json.loads((tmp_path / "reel1" / "scan.json").read_text())
    assert meta["state"] == "done"


def test_test_frame_after_scan_turns_light_back_on(tmp_path):
    film, runner = make_runner(tmp_path)
    runner.start("reel1", max_frames=2)
    wait_for(runner, {"done"})
    assert film.light == 0
    assert runner.test_frame()["detected"] is True
    assert film.light == runner.settings.light_percent


def kinds_texts(runner):
    return [(e["kind"], e["text"]) for e in runner.log_since(0)["entries"]]


def test_log_since_has_scan_events(tmp_path):
    _, runner = make_runner(tmp_path)
    runner.start("reel1", max_frames=3)
    wait_for(runner, {"done"})
    log = runner.log_since(0)
    texts = [e["text"] for e in log["entries"]]
    assert texts[0] == "scan started at frame 0" and "done: 3 frames, 0 flagged" in texts
    assert log["last_id"] == log["entries"][-1]["id"]
    assert runner.log_since(log["last_id"]) == {"entries": [], "last_id": log["last_id"]}


def test_ui_actions_are_logged(tmp_path):
    _, runner = make_runner(tmp_path)
    runner.set_light(40)
    runner.set_exposure(2000, 1.0)
    runner.test_frame()
    assert kinds_texts(runner) == [
        ("event", "light set to 40%"), ("event", "exposure 2000 us, gain 1.0"), ("event", "test frame: hole at 74, 380")]
    _, runner = make_runner(tmp_path)
    runner.camera.blank_remaining = 1
    runner.test_frame()
    assert kinds_texts(runner) == [("event", "test frame: hole not found")]


def test_console_returns_reply_and_logs_traffic(tmp_path):
    from app.console import CommandLog
    from app.controller import Controller
    from test_controller import FakePort

    log = CommandLog()
    controller = Controller(FakePort(["OK light=100"]), on_traffic=log.add)
    runner = ScanRunner(controller, FakeFilm(), Settings(flip_vertical=False, light_control=True, output_dir=str(tmp_path)), log=log)
    assert runner.log is log
    assert runner.console("status") == {"reply": "light=100"}
    assert kinds_texts(runner) == [("cmd", "STATUS"), ("reply", "OK light=100")]


def test_console_errors(tmp_path):
    from app.controller import ControllerError

    film, runner = make_runner(tmp_path)

    def refuse(line):
        raise ValueError("unknown command")  # what the real Controller.command does

    film.command = refuse
    with pytest.raises(RunnerError) as e:
        runner.console("reboot")
    assert e.value.status == 400 and str(e.value) == "unknown command"

    def broken(line):
        raise ControllerError("no reply to 'STATUS' (timeout)")

    film.command = broken
    with pytest.raises(RunnerError) as e:
        runner.console("STATUS")
    assert e.value.status == 502 and "timeout" in str(e.value)


def test_console_refused_while_scanning(tmp_path):
    film, runner = gated_runner(tmp_path)
    runner.start("reel1")
    try:
        with pytest.raises(RunnerError) as e:
            runner.console("STATUS")
        assert e.value.status == 409
        assert film.commands == []
    finally:
        film.gate.set()
        runner.stop()
        wait_for(runner, {"done"})


def test_status_new_keys(tmp_path):
    _, runner = make_runner(tmp_path)
    st = runner.status()
    assert st["flagged_frames"] == [] and st["elapsed_s"] == 0 and st["rate_fps"] == 0
    assert st["disk_free_gb"] > 0 and st["target_frac"] is None
    runner.start("reel1", max_frames=3)
    wait_for(runner, {"done"})
    st = runner.status()
    assert st["flagged_frames"] == [] and st["elapsed_s"] > 0 and st["rate_fps"] == 0
    fx, fy = st["target_frac"]
    assert 0 < fx < 1 and fy == pytest.approx(0.5)
    assert st["disk_free_gb"] > 0
    assert {"state", "name", "frame", "flagged", "error"} <= set(st)


def test_status_flagged_frames_and_rate(tmp_path, monkeypatch):
    import app.runner

    film, runner = make_runner(tmp_path)
    seen = {}

    def hook(sc):
        if sc.frame_number == 2:
            film.blank_remaining = 3
        if sc.frame_number == 5:
            seen.update(runner.status())

    class HookedScanner(Scanner):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            runner_hook = self.on_progress
            self.on_progress = lambda sc: (runner_hook(sc), hook(sc))

    runner.settings.retries = 2
    monkeypatch.setattr(app.runner, "Scanner", HookedScanner)
    runner.start("reel1", max_frames=6)
    wait_for(runner, {"done"})
    assert runner.status()["flagged_frames"] == [2]
    assert seen["rate_fps"] > 0


def test_console_light_updates_settings(tmp_path):
    film, runner = make_runner(tmp_path)
    runner.console("light 30")
    assert runner.settings.light_percent == 30
    runner.console("status")
    assert runner.settings.light_percent == 30


def fixed_light_runner(tmp_path):
    film = FakeFilm()
    return film, ScanRunner(film, film, Settings(flip_vertical=False, output_dir=str(tmp_path)))


def test_fixed_light_refuses_light_commands(tmp_path):
    film, runner = fixed_light_runner(tmp_path)
    with pytest.raises(RunnerError) as e:
        runner.set_light(30)
    assert (e.value.status, str(e.value)) == (400, "light control is disabled")
    with pytest.raises(RunnerError) as e:
        runner.console("LIGHT 30")
    assert e.value.status == 400
    assert runner.console("STATUS") == {"reply": "light=100"}
    assert film.light is None


def test_fixed_light_test_frame_leaves_light_alone(tmp_path):
    film, runner = fixed_light_runner(tmp_path)
    assert runner.test_frame()["detected"] is True
    assert film.light is None
