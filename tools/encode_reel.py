import subprocess
from pathlib import Path


def ffmpeg_command(frames_dir, out_path, fps, start_number=0):
    return [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-start_number", str(start_number),
        "-i", str(Path(frames_dir) / "frame_%08d.png"),
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # yuv420p needs even dimensions
        "-c:v", "libx264", "-preset", "slower", "-crf", "15",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]


def build_mp4(reel_dir, fps):
    reel_dir = Path(reel_dir)
    out = reel_dir / "reel.mp4"
    subprocess.run(ffmpeg_command(reel_dir / "frames", out, fps), check=True, capture_output=True)
    return out
