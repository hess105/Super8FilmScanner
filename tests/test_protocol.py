import pytest
from protocol import ProtocolError, format_err, format_ok, parse_command


def test_advance_uses_default_rate():
    assert parse_command("ADVANCE 164") == ("ADVANCE", 164, 2000)


def test_advance_with_rate_and_negative_steps():
    assert parse_command("advance -5 170\n") == ("ADVANCE", -5, 170)


def test_wind_default_rate():
    assert parse_command("WIND 1021") == ("WIND", 1021, 1500)


def test_light_and_status():
    assert parse_command("LIGHT 50") == ("LIGHT", 50)
    assert parse_command("STATUS") == ("STATUS",)


@pytest.mark.parametrize("line", [
    "", "   ", "FOO", "ADVANCE", "ADVANCE x", "ADVANCE 1 0", "ADVANCE 1 4001",
    "ADVANCE 1 2 3", "LIGHT", "LIGHT 101", "LIGHT -1", "LIGHT x", "STATUS now",
])
def test_bad_lines_raise(line):
    with pytest.raises(ProtocolError):
        parse_command(line)


def test_formatting():
    assert format_ok() == "OK"
    assert format_ok("light=50") == "OK light=50"
    assert format_err("bad") == "ERR bad"
