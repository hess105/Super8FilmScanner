import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional, Tuple


@dataclass
class Settings:
    # controller link
    serial_port: str = "/dev/ttyACM0"
    baudrate: int = 115200
    serial_timeout_s: float = 30.0
    output_dir: str = "scans"
    # film transport, in motor steps (calibrate on the machine)
    steps_per_frame: int = 164
    advance_rate: int = 2000
    nudge_forward_steps: int = 15
    nudge_reverse_steps: int = -5
    nudge_rate: int = 170
    nudge_tolerance_frac: float = 0.03  # of image height
    max_nudges: int = 25
    # take-up spool
    reel_steps_per_rev: int = 3200
    wind_rate: int = 1500
    frames_per_wind: int = 8
    frame_height_mm: float = 4.01
    film_thickness_mm: float = 0.15
    spool_inner_diameter_mm: float = 32.0
    # camera and light
    width: int = 4056
    height: int = 3040
    exposure_us: int = 2000
    gain: float = 1.0
    flip_vertical: bool = True
    light_percent: int = 100
    # sprocket detection
    sprocket_strip_frac: float = 0.16
    sprocket_threshold: int = 230
    sprocket_min_area_frac: float = 0.012
    sprocket_max_area_frac: float = 0.06
    detect_width: int = 1024
    retries: int = 3
    max_consecutive_failures: int = 5
    # output
    png_compression: int = 2
    fps: int = 18
    denoise: bool = False
    resize_to: Optional[Tuple[int, int]] = None

    @classmethod
    def load(cls, path):
        path = Path(path)
        if not path.exists():
            return cls()
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in json.loads(path.read_text()).items() if k in known}
        if isinstance(data.get("resize_to"), list):
            data["resize_to"] = tuple(data["resize_to"])
        return cls(**data)

    def save(self, path):
        Path(path).write_text(json.dumps(asdict(self), indent=2))
