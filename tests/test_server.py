import threading
import time

from fakes import FakeFilm
from fastapi.testclient import TestClient

from app.config import Settings
from app.runner import ScanRunner
from app.server import create_app


def make_client(tmp_path):
    film = FakeFilm()
    film.set_exposure = lambda us, gain: None
    settings = Settings(flip_vertical=False, light_control=True, output_dir=str(tmp_path))
    runner = ScanRunner(film, film, settings)
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


def test_settings_route(tmp_path):
    client, _ = make_client(tmp_path)
    s = client.get("/api/settings").json()
    assert s == {"light_percent": 100, "exposure_us": 2000, "gain": 1.0, "light_control": True}
    client.post("/api/light", json={"percent": 40})
    client.post("/api/exposure", json={"exposure_us": 3000, "gain": 2.5})
    assert client.get("/api/settings").json() == {"light_percent": 40, "exposure_us": 3000, "gain": 2.5, "light_control": True}


def test_bounds_and_missing_fields(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.post("/api/light", json={"percent": -1}).status_code == 422
    assert client.post("/api/light", json={}).status_code == 422
    assert client.post("/api/exposure", json={"exposure_us": 2000, "gain": 0.5}).status_code == 422
    assert client.post("/api/exposure", json={"exposure_us": 2000, "gain": 17}).status_code == 422
    assert client.post("/api/exposure", json={"gain": 1.0}).status_code == 422
    assert client.post("/api/exposure", json={"exposure_us": 2000}).status_code == 422
    assert client.post("/api/scan/start", json={}).status_code == 422
    assert client.post("/api/scan/start", json={"name": ""}).status_code == 400


def test_hardware_routes_409_while_scanning(tmp_path):
    film = FakeFilm()
    gate = threading.Event()
    orig = film.set_light

    def gated_light(percent):  # the scan thread's first set_light blocks, keeping the scan busy
        if percent != 0 and threading.current_thread().name != "MainThread":
            gate.wait(10)
        orig(percent)

    film.set_light = gated_light
    film.set_exposure = lambda us, gain: None
    settings = Settings(flip_vertical=False, light_control=True, output_dir=str(tmp_path))
    client = TestClient(create_app(ScanRunner(film, film, settings)))
    try:
        assert client.post("/api/scan/start", json={"name": "reel1"}).status_code == 200
        assert client.post("/api/light", json={"percent": 10}).status_code == 409
        assert client.post("/api/exposure", json={"exposure_us": 1000, "gain": 1.0}).status_code == 409
        assert client.post("/api/test-frame").status_code == 409
        assert client.post("/api/scan/start", json={"name": "reel2"}).status_code == 409
    finally:
        client.post("/api/scan/stop")
        gate.set()
    end = time.time() + 10
    while client.get("/api/status").json()["state"] not in ("done", "error") and time.time() < end:
        time.sleep(0.02)
    assert client.get("/api/status").json()["state"] == "done"


def test_log_route(tmp_path):
    client, _ = make_client(tmp_path)
    client.post("/api/light", json={"percent": 40})
    client.post("/api/light", json={"percent": 50})
    log = client.get("/api/log").json()
    assert [e["text"] for e in log["entries"]] == ["light set to 40%", "light set to 50%"]
    newer = client.get("/api/log", params={"since": log["entries"][0]["id"]}).json()
    assert [e["text"] for e in newer["entries"]] == ["light set to 50%"]
    assert newer["last_id"] == log["last_id"]
    assert client.get("/api/log", params={"since": -1}).status_code == 422


def refuse_unknown(line):
    raise ValueError("unknown command")  # what the real Controller.command does


def test_console_route(tmp_path):
    client, film = make_client(tmp_path)
    r = client.post("/api/console", json={"command": "status"})
    assert r.status_code == 200 and r.json() == {"reply": "light=100"}
    assert film.commands == ["status"]
    film.command = refuse_unknown
    r = client.post("/api/console", json={"command": "reboot"})
    assert r.status_code == 400 and r.json()["detail"] == "unknown command"
    assert client.post("/api/console", json={"command": ""}).status_code == 422
    assert client.post("/api/console", json={"command": "x" * 41}).status_code == 422


def test_console_route_409_while_scanning(tmp_path):
    film = FakeFilm()
    gate = threading.Event()
    orig = film.set_light

    def gated_light(percent):
        if percent != 0 and threading.current_thread().name != "MainThread":
            gate.wait(10)
        orig(percent)

    film.set_light = gated_light
    client = TestClient(create_app(ScanRunner(film, film, Settings(flip_vertical=False, light_control=True, output_dir=str(tmp_path)))))
    try:
        assert client.post("/api/scan/start", json={"name": "reel1"}).status_code == 200
        assert client.post("/api/console", json={"command": "STATUS"}).status_code == 409
    finally:
        client.post("/api/scan/stop")
        gate.set()



def test_page_has_script_element_ids(tmp_path):
    client, _ = make_client(tmp_path)
    page = client.get("/").text
    for element_id in ("terminal", "term-input", "state-pill", "preview", "btn-start"):
        assert 'id="%s"' % element_id in page


def test_controller_error_on_light_is_502(tmp_path):
    from app.controller import ControllerError
    client, film = make_client(tmp_path)

    def boom(*a):
        raise ControllerError("no reply to 'LIGHT 40' (timeout)")

    film.set_light = boom
    r = client.post("/api/light", json={"percent": 40})
    assert r.status_code == 502 and "no reply" in r.json()["detail"]


def test_fixed_light_routes(tmp_path):
    film = FakeFilm()
    client = TestClient(create_app(ScanRunner(film, film, Settings(flip_vertical=False, output_dir=str(tmp_path)))))
    assert client.get("/api/settings").json()["light_control"] is False
    assert client.post("/api/light", json={"percent": 40}).status_code == 400
    assert client.post("/api/console", json={"command": "LIGHT 30"}).status_code == 400
    assert film.light is None


def test_light_control_enabled_in_settings(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/api/settings").json()["light_control"] is True
