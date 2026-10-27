import subprocess
from pathlib import Path
import pytest

import encode_reel as er

PATTERN = "reel/frames/frame_%08d.png"
OUT = "reel/reel.mp4"

CANNED = """Encoders:
 V..... = Video
 A..... = Audio
 ------
 V....D libx264              libx264 H.264 / AVC (codec h264)
 V....D libx265              libx265 H.265 / HEVC (codec hevc)
 V....D h264_nvenc           NVIDIA NVENC H.264 encoder (codec h264)
 V....D hevc_videotoolbox    VideoToolbox H.265 Encoder (codec hevc)
 A....D aac                  AAC (Advanced Audio Coding)
"""


def cmd(encoder, codec="h264", height=None, quality=None, src=PATTERN):
    return er.build_command(src, OUT, 18, encoder, codec, height, quality)


def opt(c, flag):
    return c[c.index(flag) + 1]


def make_reel(tmp_path, numbers):
    frames = tmp_path / "frames"
    frames.mkdir(parents=True)
    for n in numbers:
        (frames / f"frame_{n:08d}.png").write_bytes(b"x")
    return tmp_path


def probe_with(text, code=0):
    def run(args, **kw):
        return subprocess.CompletedProcess(args, code, stdout=text, stderr="")
    return run


NAMES = {
    ("cpu", "h264"): "libx264", ("cpu", "hevc"): "libx265",
    ("nvenc", "h264"): "h264_nvenc", ("nvenc", "hevc"): "hevc_nvenc",
    ("videotoolbox", "h264"): "h264_videotoolbox", ("videotoolbox", "hevc"): "hevc_videotoolbox",
    ("qsv", "h264"): "h264_qsv", ("qsv", "hevc"): "hevc_qsv",
    ("amf", "h264"): "h264_amf", ("amf", "hevc"): "hevc_amf",
    ("vaapi", "h264"): "h264_vaapi", ("vaapi", "hevc"): "hevc_vaapi",
}


def test_encoder_table_is_exactly_the_documented_names():
    assert {(e, c): n for e, d in er.ENCODERS.items() for c, n in d.items()} == NAMES


@pytest.mark.parametrize("encoder,codec", list(NAMES))
def test_each_encoder_command_uses_the_exact_ffmpeg_name(encoder, codec):
    c = cmd(encoder, codec)
    assert opt(c, "-c:v") == NAMES[(encoder, codec)]
    assert c[0] == "ffmpeg" and c[-1] == OUT
    assert opt(c, "-i") == PATTERN and opt(c, "-framerate") == "18"


def test_cpu_flags_h264_and_hevc():
    for codec, name in (("h264", "libx264"), ("hevc", "libx265")):
        c = cmd("cpu", codec)
        assert opt(c, "-c:v") == name
        assert opt(c, "-preset") == "slower"
        assert opt(c, "-crf") == "15"
        assert opt(c, "-pix_fmt") == "yuv420p"
    assert opt(cmd("cpu", "hevc"), "-tag:v") == "hvc1"
    assert opt(cmd("cpu", quality=20), "-crf") == "20"


def test_scaling_even_by_default_and_height_when_given():
    assert opt(cmd("cpu"), "-vf") == "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    assert opt(cmd("cpu", height=1080), "-vf") == "scale=-2:1080"


@pytest.mark.parametrize("codec", ["h264", "hevc"])
def test_nvenc_flags(codec):
    c = cmd("nvenc", codec, quality=21)
    assert opt(c, "-rc") == "vbr" and opt(c, "-cq") == "21" and opt(c, "-b:v") == "0"


@pytest.mark.parametrize("codec", ["h264", "hevc"])
def test_videotoolbox_flags(codec):
    c = cmd("videotoolbox", codec, quality=70)
    assert opt(c, "-c:v") == er.ENCODERS["videotoolbox"][codec]
    assert opt(c, "-q:v") == "70"


@pytest.mark.parametrize("codec", ["h264", "hevc"])
def test_qsv_flags(codec):
    assert opt(cmd("qsv", codec, quality=22), "-global_quality") == "22"


@pytest.mark.parametrize("codec", ["h264", "hevc"])
def test_amf_flags(codec):
    c = cmd("amf", codec, quality=19)
    assert opt(c, "-rc") == "cqp"
    assert opt(c, "-qp_i") == "19" and opt(c, "-qp_p") == "19"


@pytest.mark.parametrize("codec", ["h264", "hevc"])
def test_vaapi_uses_device_before_input_and_hwupload(codec):
    c = cmd("vaapi", codec, height=1080, quality=23)
    assert opt(c, "-vaapi_device") == "/dev/dri/renderD128"
    assert c.index("-vaapi_device") < c.index("-i")
    assert opt(c, "-vf") == "scale=-2:1080,format=nv12,hwupload"
    assert opt(c, "-qp") == "23"
    assert "-pix_fmt" not in c


def test_default_quality_is_set_for_every_encoder():
    assert set(er.DEFAULT_QUALITY) == set(er.ENCODERS)
    assert er.DEFAULT_QUALITY["cpu"] == 15


def test_concat_list_is_used_as_input():
    c = cmd("cpu", src="/tmp/list.txt")
    assert c[c.index("-f") + 1] == "concat"
    assert opt(c, "-safe") == "0" and opt(c, "-i") == "/tmp/list.txt"
    assert "-framerate" not in c and opt(c, "-r") == "18"


def test_start_number_for_a_sequence_that_does_not_begin_at_zero():
    c = er.build_command(PATTERN, OUT, 18, "cpu", "h264", None, None, start_number=7)
    assert opt(c, "-start_number") == "7"


def test_available_encoders_parses_canned_output():
    got = er.available_encoders("ffmpeg", probe_with(CANNED))
    assert got == {"libx264", "libx265", "h264_nvenc", "hevc_videotoolbox"}
    assert {"libx264", "libx265", "h264_nvenc", "hevc_videotoolbox"} <= got


def test_available_encoders_empty_when_ffmpeg_missing():
    def boom(args, **kw):
        raise FileNotFoundError("ffmpeg")
    assert er.available_encoders("ffmpeg", boom) == set()


def test_encoder_order_auto_priority_and_cpu_last():
    av = {"libx264", "h264_vaapi", "h264_nvenc", "h264_videotoolbox"}
    assert er.encoder_order("auto", "h264", av) == ["nvenc", "videotoolbox", "vaapi", "cpu"]
    assert er.encoder_order("auto", "h264", set()) == ["cpu"]
    assert er.encoder_order("auto", "hevc", {"h264_nvenc"}) == ["cpu"]


def test_encoder_order_named_encoder_and_missing():
    assert er.encoder_order("nvenc", "h264", {"h264_nvenc"}) == ["nvenc"]
    with pytest.raises(ValueError, match="h264_nvenc"):
        er.encoder_order("nvenc", "h264", {"libx264"})


def test_find_gaps(tmp_path):
    assert er.find_gaps(make_reel(tmp_path / "a", [0, 1, 2, 3]) / "frames") == []
    assert er.find_gaps(make_reel(tmp_path / "b", [2, 3, 4]) / "frames") == []
    assert er.find_gaps(make_reel(tmp_path / "c", [0, 1, 4, 6]) / "frames") == [2, 3, 5]
    assert er.find_gaps(tmp_path / "nothing") == []


def test_concat_list_contents(tmp_path):
    frames = make_reel(tmp_path, [0, 1, 3]) / "frames"
    lst = er.write_concat_list(frames, 20, tmp_path / "list.txt")
    lines = lst.read_text().splitlines()
    f = lambda n: f"file '{frames / f'frame_{n:08d}.png'}'"
    assert lines == [f(0), "duration 0.050000", f(1), "duration 0.050000", f(3), "duration 0.050000"]


def test_parse_progress():
    assert er.parse_progress("frame=1234") == 1234
    assert er.parse_progress("frame=   7\n") == 7
    assert er.parse_progress("fps=18.0") is None
    assert er.parse_progress("progress=continue") is None
    assert er.parse_progress("") is None


def test_progress_line_printed_at_most_once_a_second():
    out, now = [], [0.0]
    on_frame = er.progress_printer(3600, out.append, clock=lambda: now[0])
    on_frame(1)
    now[0] = 0.4
    on_frame(500)
    now[0] = 1.2
    on_frame(1234)
    assert out == ["frame 1/3600 (0%)", "frame 1234/3600 (34%)"]


def test_fallback_tries_next_encoder_and_reports_which_produced_the_file(tmp_path, capsys):
    reel = make_reel(tmp_path, [0, 1, 2])
    seen = []

    def encode(command, on_frame):
        seen.append(opt(command, "-c:v"))
        if len(seen) == 1:
            return 1, "Error initializing output stream: Cannot load libcuda.so.1"
        Path(command[-1]).write_bytes(b"mp4")
        return 0, ""

    probe = probe_with(CANNED)
    code = er.main([str(reel)], probe=probe, encode=encode)
    out, err = capsys.readouterr()
    assert code == 0
    assert seen == ["h264_nvenc", "libx264"]
    assert "libcuda" in err and "wrote" in out and out.strip().endswith("using cpu")


def test_named_encoder_does_not_fall_back(tmp_path):
    reel = make_reel(tmp_path, [0, 1])
    seen = []

    def encode(command, on_frame):
        seen.append(1)
        return 1, "Error initializing"

    assert er.main([str(reel), "--encoder", "cpu"], probe=probe_with(CANNED), encode=encode) == 1
    assert len(seen) == 1


def test_all_encoders_failing_returns_1(tmp_path):
    reel = make_reel(tmp_path, [0, 1])
    code = er.main([str(reel)], probe=probe_with(CANNED), encode=lambda c, f: (1, "boom"))
    assert code == 1


def test_dry_run_prints_the_command_and_does_not_run_ffmpeg(tmp_path, capsys):
    reel = make_reel(tmp_path, [0, 1, 2])

    def never(command, on_frame):
        raise AssertionError("must not run")

    code = er.main([str(reel), "--dry-run", "--encoder", "cpu"], probe=probe_with(CANNED), encode=never)
    out = capsys.readouterr().out
    assert code == 0
    assert "libx264" in out and str(reel / "reel.part.mp4") in out and "frame_%08d.png" in out


def test_dry_run_with_gaps_warns_and_uses_a_concat_list(tmp_path, capsys):
    reel = make_reel(tmp_path, [0, 1, 4])
    code = er.main([str(reel), "--dry-run", "--encoder", "cpu"], probe=probe_with(CANNED))
    out = capsys.readouterr().out
    assert code == 0
    assert "missing" in out and "2, 3" in out and "concat" in out


def test_output_option(tmp_path, capsys):
    reel = make_reel(tmp_path, [0])
    er.main([str(reel), "--dry-run", "--encoder", "cpu", "--output", str(tmp_path / "x.mp4")],
            probe=probe_with(CANNED))
    assert str(tmp_path / "x.part.mp4") in capsys.readouterr().out


def test_list_encoders_needs_no_reel(capsys):
    assert er.main(["--list-encoders"], probe=probe_with(CANNED)) == 0
    out = capsys.readouterr().out
    assert "h264_nvenc" in out and "would use" in out and "nvenc" in out


def test_bad_arguments_return_2(tmp_path):
    reel = make_reel(tmp_path, [0])
    probe = probe_with(CANNED)
    assert er.main([], probe=probe) == 2
    assert er.main([str(tmp_path / "nope")], probe=probe) == 2
    assert er.main([str(reel), "--encoder", "bogus"], probe=probe) == 2
    assert er.main([str(reel), "--fps", "0"], probe=probe) == 2
    assert er.main([str(reel), "--height", "-1"], probe=probe) == 2
    assert er.main([str(reel), "--encoder", "nvenc", "--dry-run"], probe=probe_with("")) == 2
    empty = tmp_path / "empty"
    (empty / "frames").mkdir(parents=True)
    assert er.main([str(empty)], probe=probe) == 2


def test_cpu_path_command_is_the_documented_manual_line():
    c = cmd("cpu")
    assert c[c.index("-c:v"):c.index("-c:v") + 4] == ["-c:v", "libx264", "-preset", "slower"]


def part_of(out):
    return out.with_name(out.stem + ".part" + out.suffix)


def test_failed_start_keeps_an_existing_output(tmp_path):
    reel = make_reel(tmp_path, [0, 1])
    (reel / "reel.mp4").write_bytes(b"old")
    code = er.main([str(reel), "--encoder", "cpu"], probe=probe_with(CANNED),
                   encode=lambda c, f: (127, "cannot run ffmpeg"))
    assert code == 1
    assert (reel / "reel.mp4").read_bytes() == b"old"
    assert not part_of(reel / "reel.mp4").exists()


def test_failed_encode_keeps_an_existing_output_and_removes_the_part_file(tmp_path):
    reel = make_reel(tmp_path, [0, 1])
    (reel / "reel.mp4").write_bytes(b"old")

    def encode(command, on_frame):
        Path(command[-1]).write_bytes(b"half")
        return 1, "disk full"

    assert er.main([str(reel), "--encoder", "cpu"], probe=probe_with(CANNED), encode=encode) == 1
    assert (reel / "reel.mp4").read_bytes() == b"old"
    assert not part_of(reel / "reel.mp4").exists()


def test_success_replaces_the_output_and_leaves_no_part_file(tmp_path):
    reel = make_reel(tmp_path, [0, 1])
    (reel / "reel.mp4").write_bytes(b"old")

    def encode(command, on_frame):
        assert command[-1] == str(part_of(reel / "reel.mp4"))
        Path(command[-1]).write_bytes(b"new")
        return 0, ""

    assert er.main([str(reel), "--encoder", "cpu"], probe=probe_with(CANNED), encode=encode) == 0
    assert (reel / "reel.mp4").read_bytes() == b"new"
    assert not part_of(reel / "reel.mp4").exists()


def test_dry_run_shows_the_part_path(tmp_path, capsys):
    reel = make_reel(tmp_path, [0])
    er.main([str(reel), "--dry-run", "--encoder", "cpu"], probe=probe_with(CANNED))
    assert "reel.part.mp4" in capsys.readouterr().out


def test_quality_must_be_an_integer(tmp_path, capsys):
    reel = make_reel(tmp_path, [0])
    assert er.main([str(reel), "--quality", "20.5"], probe=probe_with(CANNED)) == 2
    assert er.main([str(reel), "--dry-run", "--encoder", "cpu", "--quality", "20"],
                   probe=probe_with(CANNED)) == 0
    assert "-crf 20 " in capsys.readouterr().out
