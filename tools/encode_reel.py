"""Encode a scanned reel (REEL_DIR/frames/frame_%08d.png) to MP4 on a desktop with ffmpeg.

Standard library only. The Pi never imports this file.
"""
import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ENCODERS = {
    "cpu": {"h264": "libx264", "hevc": "libx265"},
    "nvenc": {"h264": "h264_nvenc", "hevc": "hevc_nvenc"},
    "videotoolbox": {"h264": "h264_videotoolbox", "hevc": "hevc_videotoolbox"},
    "qsv": {"h264": "h264_qsv", "hevc": "hevc_qsv"},
    "amf": {"h264": "h264_amf", "hevc": "hevc_amf"},
    "vaapi": {"h264": "h264_vaapi", "hevc": "hevc_vaapi"},
}
AUTO_ORDER = ["nvenc", "videotoolbox", "qsv", "amf", "vaapi", "cpu"]
# One number per encoder; meaning differs (see build_command). Only cpu (crf 15) comes from
# the legacy workflow; the rest are starting points that have not been checked on hardware.
DEFAULT_QUALITY = {"cpu": 15, "nvenc": 19, "videotoolbox": 65, "qsv": 20, "amf": 18, "vaapi": 20}
VAAPI_DEVICE = "/dev/dri/renderD128"
FRAME_RE = re.compile(r"frame_(\d{8})\.png$")
# A non-zero exit after this many seconds is a real encode error, not an encoder that failed to start.
STARTUP_SECONDS = 10
INIT_ERRORS = ("error initializing", "could not open encoder", "cannot load", "no nvenc",
               "openencodesession", "failed to set value", "no device", "device creation failed",
               "unknown encoder", "not supported")


def available_encoders(ffmpeg="ffmpeg", runner=subprocess.run):
    """Names of the video encoders this ffmpeg lists. Empty set if ffmpeg cannot be run."""
    try:
        res = runner([ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True)
    except OSError:
        return set()
    names = set()
    for line in (res.stdout or "").splitlines():
        m = re.match(r"^\s*V[.A-Z]{5}\s+(\S+)", line)
        if m and m.group(1) != "=":
            names.add(m.group(1))
    return names


def encoder_order(requested, codec, available):
    if requested != "auto":
        name = ENCODERS[requested][codec]
        if name not in available:
            raise ValueError(f"this ffmpeg has no {name} encoder")
        return [requested]
    return [e for e in AUTO_ORDER if e == "cpu" or ENCODERS[e][codec] in available]


def build_command(frames_or_list, out_path, fps, encoder, codec, height, quality,
                  start_number=0, ffmpeg="ffmpeg"):
    """frames_or_list: a printf pattern for the PNG sequence, or a path ending in .txt (concat list)."""
    q = DEFAULT_QUALITY[encoder] if quality is None else quality
    scale = f"scale=-2:{height}" if height else "scale=trunc(iw/2)*2:trunc(ih/2)*2"  # yuv420p needs even sizes
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1"]
    if encoder == "vaapi":
        cmd += ["-vaapi_device", VAAPI_DEVICE]
    if str(frames_or_list).endswith(".txt"):
        cmd += ["-f", "concat", "-safe", "0", "-i", str(frames_or_list), "-r", str(fps)]
    else:
        cmd += ["-framerate", str(fps), "-start_number", str(start_number), "-i", str(frames_or_list)]
    cmd += ["-vf", scale + (",format=nv12,hwupload" if encoder == "vaapi" else ""),
            "-c:v", ENCODERS[encoder][codec]]
    if encoder == "cpu":
        cmd += ["-preset", "slower", "-crf", str(q)]
    elif encoder == "nvenc":
        cmd += ["-rc", "vbr", "-cq", str(q), "-b:v", "0"]
    elif encoder == "videotoolbox":
        cmd += ["-q:v", str(q)]
    elif encoder == "qsv":
        cmd += ["-global_quality", str(q)]
    elif encoder == "amf":
        cmd += ["-rc", "cqp", "-qp_i", str(q), "-qp_p", str(q)]
    else:
        cmd += ["-qp", str(q)]
    if encoder != "vaapi":
        cmd += ["-pix_fmt", "nv12" if encoder == "qsv" else "yuv420p"]
    if codec == "hevc":
        cmd += ["-tag:v", "hvc1"]  # lets QuickTime and Apple devices play it
    return cmd + [str(out_path)]


def frame_numbers(frames_dir):
    d = Path(frames_dir)
    if not d.is_dir():
        return []
    return sorted(int(m.group(1)) for p in d.iterdir() if (m := FRAME_RE.search(p.name)))


def find_gaps(frames_dir):
    nums = frame_numbers(frames_dir)
    if not nums:
        return []
    have = set(nums)
    return [n for n in range(nums[0], nums[-1] + 1) if n not in have]


def write_concat_list(frames_dir, fps, dest):
    frames_dir = Path(frames_dir)
    names = [frames_dir / f"frame_{n:08d}.png" for n in frame_numbers(frames_dir)]
    lines = []
    for p in names:
        lines += [f"file '{str(p).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'",
                  f"duration {1 / fps:.6f}"]
    Path(dest).write_text("\n".join(lines) + "\n")
    return Path(dest)


def parse_progress(line):
    m = re.match(r"^\s*frame=\s*(\d+)\s*$", line)
    return int(m.group(1)) if m else None


def progress_printer(total, out=print, clock=time.monotonic):
    last = [None]

    def on_frame(n):
        now = clock()
        if last[0] is None or now - last[0] >= 1:
            last[0] = now
            out(f"frame {n}/{total} ({100 * n // total if total else 0}%)")
    return on_frame


def run_ffmpeg(cmd, on_frame):
    """Run ffmpeg, feed frame numbers to on_frame. Returns (exit code, last error lines)."""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except OSError as e:
        return 127, f"cannot run {cmd[0]}: {e}"
    tail = []
    for line in proc.stdout:
        n = parse_progress(line)
        if n is not None:
            on_frame(n)
        elif line.strip() and "=" not in line.split()[0]:  # skip key=value progress lines
            tail = (tail + [line.strip()])[-10:]
    return proc.wait(), "\n".join(tail)


def _startup_failure(code, seconds, detail):
    return code != 0 and (seconds < STARTUP_SECONDS or any(s in detail.lower() for s in INIT_ERRORS))


def _parser():
    p = argparse.ArgumentParser(prog="encode_reel.py", description="Encode a scanned reel to MP4 with ffmpeg.")
    p.add_argument("reel_dir", nargs="?", help="reel folder containing frames/frame_%%08d.png")
    p.add_argument("--output", help="output file (default REEL_DIR/reel.mp4)")
    p.add_argument("--fps", type=int, default=18)
    p.add_argument("--encoder", default="auto", choices=["auto", *ENCODERS])
    p.add_argument("--codec", default="h264", choices=["h264", "hevc"])
    p.add_argument("--height", type=int, help="scale to this height (width follows)")
    p.add_argument("--quality", type=int, help="one number; meaning depends on the encoder, see the README")
    p.add_argument("--dry-run", action="store_true", help="print the ffmpeg command and exit")
    p.add_argument("--list-encoders", action="store_true")
    p.add_argument("--ffmpeg", default="ffmpeg", help="path to the ffmpeg program")
    return p


def main(argv=None, probe=subprocess.run, encode=run_ffmpeg):
    try:
        a = _parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2

    def bad(msg):
        print(f"error: {msg}", file=sys.stderr)
        return 2

    if a.fps <= 0 or (a.height is not None and a.height <= 0) or (a.quality is not None and a.quality < 0):
        return bad("--fps and --height must be positive and --quality not negative")
    available = available_encoders(a.ffmpeg, probe)

    if a.list_encoders:
        for e in ENCODERS:
            name = ENCODERS[e][a.codec]
            print(f"{e:13} {name:19} {'available' if name in available else 'not in this ffmpeg'}")
        print(f"would use ({a.codec}, auto): {', '.join(encoder_order('auto', a.codec, available))}")
        return 0
    if not a.reel_dir:
        return bad("REEL_DIR is required")
    reel = Path(a.reel_dir)
    frames = reel / "frames"
    nums = frame_numbers(frames)
    if not nums:
        return bad(f"no frame_%08d.png files in {frames}")
    try:
        order = encoder_order(a.encoder, a.codec, available)
    except ValueError as e:
        return bad(str(e))

    out = Path(a.output) if a.output else reel / "reel.mp4"
    gaps = find_gaps(frames)
    tmp = None
    if gaps:
        shown = ", ".join(map(str, gaps[:50])) + (f" and {len(gaps) - 50} more" if len(gaps) > 50 else "")
        print(f"warning: {len(gaps)} frames missing, playback skips them: {shown}")
        tmp = Path(tempfile.mkdtemp(prefix="encode_reel_"))
        source = str(write_concat_list(frames, a.fps, tmp / "frames.txt"))
        print(f"using concat list {source}")
    else:
        source = str(frames / "frame_%08d.png")

    part = out.with_name(out.stem + ".part" + out.suffix)  # same folder, so os.replace is atomic

    def command(e):
        return build_command(source, part, a.fps, e, a.codec, a.height, a.quality, nums[0], a.ffmpeg)

    try:
        if a.dry_run:
            print(shlex.join(command(order[0])))
            return 0
        for i, e in enumerate(order):
            print(f"encoding {len(nums)} frames with {e} ({ENCODERS[e][a.codec]})")
            started = time.monotonic()
            code, detail = encode(command(e), progress_printer(len(nums)))
            if code == 0:
                os.replace(part, out)
                print(f"wrote {out} using {e}")
                return 0
            part.unlink(missing_ok=True)  # never touches an existing output
            print(f"{e} failed (exit {code}): {detail or 'no message'}", file=sys.stderr)
            if i + 1 == len(order) or not _startup_failure(code, time.monotonic() - started, detail):
                return 1
            print(f"trying {order[i + 1]} instead")
        return 1
    finally:
        if tmp and not a.dry_run:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
