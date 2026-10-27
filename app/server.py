from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from .controller import ControllerError
from .runner import RunnerError

STATIC = Path(__file__).parent / "static"


class StartRequest(BaseModel):
    name: str


class LightRequest(BaseModel):
    percent: int = Field(ge=0, le=100)


class ExposureRequest(BaseModel):
    exposure_us: int = Field(gt=0)
    gain: float = Field(ge=1.0, le=16.0)


class ConsoleRequest(BaseModel):
    command: str = Field(min_length=1, max_length=40)


def create_app(runner):
    app = FastAPI(title="Super 8 Scanner")

    def call(fn, *args):
        try:
            return fn(*args)
        except RunnerError as e:
            raise HTTPException(e.status, str(e))
        except ControllerError as e:
            raise HTTPException(502, str(e))

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    def status():
        return runner.status()

    @app.get("/api/settings")
    def settings():
        st = runner.settings
        return {"light_percent": st.light_percent, "exposure_us": st.exposure_us, "gain": st.gain}

    @app.post("/api/scan/start")
    def start(req: StartRequest):
        call(runner.start, req.name)
        return runner.status()

    @app.post("/api/scan/pause")
    def pause():
        runner.pause()
        return runner.status()

    @app.post("/api/scan/resume")
    def resume():
        runner.resume()
        return runner.status()

    @app.post("/api/scan/stop")
    def stop():
        runner.stop()
        return runner.status()

    @app.get("/api/preview.jpg")
    def preview():
        return Response(call(runner.preview_jpeg), media_type="image/jpeg")

    @app.post("/api/test-frame")
    def test_frame():
        return call(runner.test_frame)

    @app.post("/api/light")
    def light(req: LightRequest):
        call(runner.set_light, req.percent)
        return {"percent": req.percent}

    @app.post("/api/exposure")
    def exposure(req: ExposureRequest):
        call(runner.set_exposure, req.exposure_us, req.gain)
        return {"exposure_us": req.exposure_us, "gain": req.gain}

    @app.get("/api/log")
    def log(since: int = Query(0, ge=0)):
        return runner.log_since(since)

    @app.post("/api/console")
    def console(req: ConsoleRequest):
        return call(runner.console, req.command)

    return app
