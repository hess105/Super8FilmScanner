import json
import threading
import time

import cv2
import pytest
from fakes import FakeFilm

from app.align import detect_sprocket
from app.config import Settings
from app.scan import Scanner, next_frame_number


def settings(**kw):
    return Settings(flip_vertical=False, **kw)


def scanner(film, tmp_path, s=None, **kw):
    return Scanner(film, film, s or settings(), tmp_path / "reel", **kw)


def test_saves_aligned_uncropped_frames(tmp_path):
    film = FakeFilm()
    sc = scanner(film, tmp_path)
    sc.run(max_frames=12)
    assert sc.state == "done"
    assert sc.frame_number == 12
    assert film.light == 0  # light is switched off afterwards
    frames = sorted((tmp_path / "reel" / "frames").glob("frame_*.png"))
    assert [p.name for p in frames] == ["frame_%08d.png" % i for i in range(12)]
    for p in frames:
        img = cv2.imread(str(p))
        assert img.shape[:2] == (600, 800)  # nothing cropped
        cx, cy = detect_sprocket(img, settings())
        assert cx == pytest.approx(sc.target[0], abs=1.5)
        assert cy == pytest.approx(sc.target[1], abs=1.5)  # hole sits on the target row


def test_winds_take_up_spool_after_enough_frames(tmp_path):
    film = FakeFilm()
    scanner(film, tmp_path).run(max_frames=12)
    assert len(film.winds) == 1 and film.winds[0] > 0


def test_blank_capture_is_flagged_and_scan_continues(tmp_path):
    film = FakeFilm()

    def hook(sc):
        if sc.frame_number == 2:
            film.blank_remaining = 3  # frame 2 and both retries are blank

    sc = scanner(film, tmp_path, settings(retries=2), on_progress=hook)
    sc.run(max_frames=6)
    assert sc.flagged == [2]
    assert sc.frame_number == 6
    assert json.loads((tmp_path / "reel" / "scan.json").read_text())["flagged"] == [2]


def test_lost_sprocket_stops_the_scan(tmp_path):
    film = FakeFilm()
    film.blank_remaining = 10 ** 6
    sc = scanner(film, tmp_path, settings(retries=0, max_consecutive_failures=3))
    sc.run(max_frames=50)
    assert sc.state == "error"
    assert "lost" in sc.error
    assert sc.frame_number == 2


def test_too_many_nudges_stops_the_scan(tmp_path):
    sc = scanner(FakeFilm(), tmp_path, settings(max_nudges=2))
    sc.run(max_frames=5)
    assert sc.state == "error"
    assert "nudges" in sc.error


def test_resume_continues_numbering_and_target(tmp_path):
    film = FakeFilm()
    first = scanner(film, tmp_path)
    first.run(max_frames=3)
    second = scanner(film, tmp_path)
    assert second.frame_number == 3
    assert second.target == pytest.approx(first.target)
    second.run(max_frames=3)
    assert next_frame_number(tmp_path / "reel" / "frames") == 6


def test_stop_before_run_does_nothing(tmp_path):
    sc = scanner(FakeFilm(), tmp_path)
    sc.stop()
    sc.run()
    assert sc.frame_number == 0
    assert sc.state == "done"


def run_in_thread(sc, **kw):
    th = threading.Thread(target=sc.run, kwargs=kw)
    th.start()
    return th


def test_stop_while_paused_moves_nothing(tmp_path):
    film = FakeFilm()
    sc = scanner(film, tmp_path)
    sc.pause()
    th = run_in_thread(sc)
    time.sleep(0.2)
    sc.stop()
    th.join(5)
    assert not th.is_alive()
    assert film.pos == 0 and sc.frame_number == 0


def test_pause_then_resume_completes(tmp_path):
    film = FakeFilm()
    sc = scanner(film, tmp_path)
    sc.pause()
    th = run_in_thread(sc, max_frames=4)
    time.sleep(0.2)
    assert sc.frame_number == 0
    sc.resume()
    th.join(10)
    assert not th.is_alive()
    assert sc.state == "done" and sc.frame_number == 4


def test_failed_write_is_flagged_and_reported(tmp_path):
    sc = scanner(FakeFilm(), tmp_path)
    real = sc._write

    def write(path, image):
        if path.name == "frame_00000003.png":
            raise IOError("disk full")
        real(path, image)

    sc._write = write
    sc.run(max_frames=10)
    assert sc.state == "error"
    assert 3 in sc.flagged
    assert "frame 3 write failed" in sc.error and "disk full" in sc.error
    assert 3 in json.loads((tmp_path / "reel" / "scan.json").read_text())["flagged"]


def test_nudge_counter_resets_between_frames(tmp_path):
    sc = scanner(FakeFilm(), tmp_path, settings(max_nudges=6))
    sc.run(max_frames=20)
    assert sc.state == "done", sc.error


def test_failure_counter_resets_after_recovery(tmp_path):
    film = FakeFilm()

    def hook(sc):
        if sc.frame_number in (1, 3, 5, 7):
            film.blank_remaining = 1

    sc = scanner(film, tmp_path, settings(retries=0, max_consecutive_failures=2), on_progress=hook)
    sc.run(max_frames=9)
    assert sc.state == "done", sc.error
    assert sc.flagged == [1, 3, 5, 7]


def test_error_turns_light_off_and_saves_state(tmp_path):
    film = FakeFilm()
    film.blank_remaining = 10 ** 6
    sc = scanner(film, tmp_path, settings(retries=0, max_consecutive_failures=3))
    sc.run(max_frames=50)
    assert film.light == 0
    assert json.loads((tmp_path / "reel" / "scan.json").read_text())["state"] == "error"


def test_meta_saved_during_scan_and_corrupt_meta_tolerated(tmp_path):
    film = FakeFilm()
    seen = {}

    def hook(sc):
        if sc.frame_number == 2:
            seen.update(json.loads((tmp_path / "reel" / "scan.json").read_text()))

    scanner(film, tmp_path, on_progress=hook).run(max_frames=3)
    assert seen["target"] is not None  # saved before run() ended
    (tmp_path / "reel" / "scan.json").write_text('{"target": [1, ')
    sc = scanner(film, tmp_path)
    assert sc.target is None and sc.flagged == [] and sc.frame_number == 3


def test_no_tmp_png_left_and_stray_tmp_is_not_counted(tmp_path):
    film = FakeFilm()
    sc = scanner(film, tmp_path)
    sc.run(max_frames=3)
    frames = tmp_path / "reel" / "frames"
    assert list(frames.glob("*.tmp.png")) == []
    (frames / "frame_00000007.tmp.png").write_bytes(b"x")
    assert next_frame_number(frames) == 3


def test_events_for_start_nudge_flag_wind_and_finish(tmp_path):
    film = FakeFilm()
    events = []

    def hook(sc):
        if sc.frame_number == 2:
            film.blank_remaining = 3

    sc = scanner(film, tmp_path, settings(retries=2), on_progress=hook, on_event=events.append)
    sc.run(max_frames=12)
    assert events[0] == "scan started at frame 0"
    assert any(e.startswith("target set") for e in events)
    nudges = [e for e in events if e.startswith("nudge")]
    assert nudges and "forward 15 steps" in nudges[0] and "px below target" in nudges[0]
    assert any("frame 2 flagged" in e for e in events)
    assert sum(e.startswith("wind ") and e.endswith(" steps") for e in events) == 1
    assert events[-1] == "done: 12 frames, 1 flagged"
    # no event per good frame: start, target, nudges, one flag, one wind, done
    assert len(events) == 5 + len(nudges)


def test_events_for_pause_resume_stop_and_error(tmp_path):
    events = []
    sc = scanner(FakeFilm(), tmp_path, settings(max_nudges=2), on_event=events.append)
    sc.pause()
    sc.resume()
    sc.stop()
    assert events == ["paused", "resumed", "stop requested"]
    events.clear()
    sc = scanner(FakeFilm(), tmp_path, settings(max_nudges=2), on_event=events.append)
    sc.run(max_frames=5)
    assert events[-1].startswith("error: ") and "nudges" in events[-1]
