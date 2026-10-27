import time

from fakes import FakeFilm
from fastapi.testclient import TestClient

from app.config import Settings
from app.runner import ScanRunner
from app.server import create_app


def make_client(tmp_path):
    film = FakeFilm()
    film.set_exposure = lambda us, gain: None
    settings = Settings(flip_vertical=False, output_dir=str(tmp_path))
    runner = ScanRunner(film, film, settings, build_video=lambda d, fps: None)
    return TestClient(create_app(runner)), film


def test_page_and_idle_status(tmp_path):
    client, _ = make_client(tmp_path)
    assert "<title>" in client.get("/").text
    assert client.get("/api/status").json()["state"] == "idle"


def test_preview_and_test_frame(tmp_path):
    client, _ = make_client(tmp_path)
    r = client.get("/api/preview.jpg")
    assert r.headers["content-type"] == "image/jpeg"
    assert client.post("/api/test-frame").json()["detected"] is True


def test_light_and_exposure_validation(tmp_path):
    client, film = make_client(tmp_path)
    assert client.post("/api/light", json={"percent": 40}).status_code == 200
    assert film.light == 40
    assert client.post("/api/light", json={"percent": 101}).status_code == 422
    assert client.post("/api/exposure", json={"exposure_us": 0, "gain": 1.0}).status_code == 422
    assert client.post("/api/exposure", json={"exposure_us": 2000, "gain": 1.0}).status_code == 200


def test_start_stop_and_errors(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.post("/api/scan/start", json={"name": "../evil"}).status_code == 400
    assert client.post("/api/scan/start", json={"name": "reel1"}).status_code == 200
    assert client.post("/api/scan/start", json={"name": "reel2"}).status_code == 409
    assert client.post("/api/scan/pause").status_code == 200
    assert client.post("/api/scan/resume").status_code == 200
    assert client.post("/api/scan/stop").status_code == 200
    end = time.time() + 10
    while client.get("/api/status").json()["state"] not in ("done", "error") and time.time() < end:
        time.sleep(0.02)
    assert client.get("/api/status").json()["state"] == "done"
