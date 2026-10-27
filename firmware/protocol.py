# Line protocol between the Pi and the RP2040. Pure Python so it runs on
# MicroPython and in host tests.

DEFAULT_RATE = {"ADVANCE": 2000, "WIND": 1500}  # steps per second
MAX_RATE = 4000


class ProtocolError(Exception):
    pass


def _int(text, name):
    try:
        return int(text)
    except ValueError:
        raise ProtocolError("bad " + name)


def parse_command(line):
    parts = line.strip().split()
    if not parts:
        raise ProtocolError("empty")
    name = parts[0].upper()
    args = parts[1:]
    if name in ("ADVANCE", "WIND"):
        if not 1 <= len(args) <= 2:
            raise ProtocolError("usage: %s <steps> [rate]" % name)
        steps = _int(args[0], "steps")
        rate = _int(args[1], "rate") if len(args) == 2 else DEFAULT_RATE[name]
        if not 1 <= rate <= MAX_RATE:
            raise ProtocolError("rate out of range")
        return (name, steps, rate)
    if name == "LIGHT":
        if len(args) != 1:
            raise ProtocolError("usage: LIGHT <0-100>")
        percent = _int(args[0], "percent")
        if not 0 <= percent <= 100:
            raise ProtocolError("percent out of range")
        return (name, percent)
    if name == "STATUS":
        if args:
            raise ProtocolError("usage: STATUS")
        return (name,)
    raise ProtocolError("unknown command")


def format_ok(extra=""):
    return "OK " + extra if extra else "OK"


def format_err(message):
    return "ERR " + message
