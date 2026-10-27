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
