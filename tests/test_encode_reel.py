from pathlib import Path

from encode_reel import ffmpeg_command


def test_command_reads_the_frame_sequence_and_writes_the_mp4():
    cmd = ffmpeg_command(Path("reel/frames"), Path("reel/reel.mp4"), 18)
    assert cmd[0] == "ffmpeg"
    assert cmd[cmd.index("-framerate") + 1] == "18"
    assert cmd[cmd.index("-i") + 1] == "reel/frames/frame_%08d.png"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[-1] == "reel/reel.mp4"
