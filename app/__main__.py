import argparse

import uvicorn

from .camera import Picamera2Camera
from .config import Settings
from .controller import Controller
from .runner import ScanRunner
from .server import create_app


def main():
    parser = argparse.ArgumentParser(description="Super 8 scanner web app")
    parser.add_argument("--config", default="scanner.json")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    settings = Settings.load(args.config)
    controller = Controller.open(settings)
    controller.set_light(settings.light_percent)
    camera = Picamera2Camera(settings)
    camera.lock_white_balance()  # with the scanner light on and empty gate
    runner = ScanRunner(controller, camera, settings)
    uvicorn.run(create_app(runner), host="0.0.0.0", port=args.port)  # LAN only, no auth in v1


if __name__ == "__main__":
    main()
