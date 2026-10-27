import pytest

from app.controller import Controller, ControllerError


class FakePort:
    def __init__(self, replies):
        self.replies = list(replies)
        self.written = []

    def reset_input_buffer(self):
        pass

    def write(self, data):
        self.written.append(data.decode())

    def readline(self):
        return (self.replies.pop(0) + "\n").encode() if self.replies else b""

    def close(self):
        pass


def test_commands_are_formatted():
    port = FakePort(["OK"] * 5)
    c = Controller(port)
    c.advance(164, 2000)
    c.advance(-5)
    c.wind(1021, 1500)
    c.wind(10)
    c.set_light(50)
    assert port.written == [
        "ADVANCE 164 2000\n", "ADVANCE -5\n", "WIND 1021 1500\n", "WIND 10\n", "LIGHT 50\n",
    ]


def test_status_returns_text_after_ok():
    assert Controller(FakePort(["OK light=50"])).status() == "light=50"


def test_err_reply_raises():
    with pytest.raises(ControllerError, match="rate out of range"):
        Controller(FakePort(["ERR rate out of range"])).advance(1, 99999)


def test_silence_raises_timeout():
    with pytest.raises(ControllerError, match="timeout"):
        Controller(FakePort([])).status()


def test_unexpected_reply_raises():
    with pytest.raises(ControllerError, match="unexpected"):
        Controller(FakePort(["hello"])).status()


def traffic_controller(replies):
    seen = []
    return Controller(FakePort(replies), on_traffic=lambda kind, text: seen.append((kind, text))), seen


def test_traffic_hook_sees_command_then_reply():
    c, seen = traffic_controller(["OK light=50"])
    c.status()
    assert seen == [("cmd", "STATUS"), ("reply", "OK light=50")]


@pytest.mark.parametrize("replies", [["ERR bad"], [], ["hello"]])
def test_traffic_hook_sees_error_before_raise(replies):
    c, seen = traffic_controller(replies)
    with pytest.raises(ControllerError) as e:
        c.status()
    assert seen[0] == ("cmd", "STATUS")
    assert seen[-1] == ("error", str(e.value))


def test_command_sends_allowed_lines():
    port = FakePort(["OK light=100", "OK"])
    c = Controller(port)
    assert c.command("  status ") == "light=100"
    assert c.command("light 30") == ""
    assert port.written == ["STATUS\n", "LIGHT 30\n"]


@pytest.mark.parametrize("line", ["reboot", "", "   ", "STATUS\nLIGHT 0", "\n", "LIGHT " + "1" * 35])
def test_command_rejects_bad_lines(line):
    port = FakePort(["OK"])
    with pytest.raises(ValueError, match="unknown command"):
        Controller(port).command(line)
    assert port.written == []
