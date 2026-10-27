class ControllerError(Exception):
    pass


COMMANDS = ("ADVANCE", "WIND", "LIGHT", "STATUS")
MAX_COMMAND = 40


class Controller:
    def __init__(self, port, on_traffic=None):
        self._port = port
        self._on_traffic = on_traffic or (lambda kind, text: None)

    @classmethod
    def open(cls, settings, on_traffic=None):
        import serial

        port = serial.Serial(settings.serial_port, settings.baudrate, timeout=settings.serial_timeout_s)
        return cls(port, on_traffic)

    def _fail(self, message):
        self._on_traffic("error", message)
        raise ControllerError(message)

    def _send(self, line):
        self._on_traffic("cmd", line)
        self._port.reset_input_buffer()
        self._port.write((line + "\n").encode("ascii"))
        reply = self._port.readline().decode("ascii", "replace").strip()
        if not reply:
            self._fail("no reply to %r (timeout)" % line)
        if reply.startswith("ERR"):
            self._fail("%s: %s" % (line, reply))
        if reply != "OK" and not reply.startswith("OK "):
            self._fail("unexpected reply to %r: %r" % (line, reply))
        self._on_traffic("reply", reply)
        return reply[2:].strip()

    def command(self, line):
        """Send one operator-typed line; only the four protocol commands are allowed."""
        line = line.strip()
        parts = line.split()
        if (not parts or len(line) > MAX_COMMAND or parts[0].upper() not in COMMANDS
                or not all(" " <= c <= "~" for c in line)):
            raise ValueError("unknown command")
        return self._send(" ".join([parts[0].upper()] + parts[1:]))

    def _move(self, name, steps, rate):
        line = "%s %d" % (name, steps)
        if rate is not None:
            line += " %d" % rate
        self._send(line)

    def advance(self, steps, rate=None):
        self._move("ADVANCE", steps, rate)

    def wind(self, steps, rate=None):
        self._move("WIND", steps, rate)

    def set_light(self, percent):
        self._send("LIGHT %d" % percent)

    def status(self):
        return self._send("STATUS")

    def close(self):
        self._port.close()
