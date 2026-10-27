class ControllerError(Exception):
    pass


class Controller:
    def __init__(self, port):
        self._port = port

    @classmethod
    def open(cls, settings):
        import serial

        return cls(serial.Serial(settings.serial_port, settings.baudrate, timeout=settings.serial_timeout_s))

    def _send(self, line):
        self._port.reset_input_buffer()
        self._port.write((line + "\n").encode("ascii"))
        reply = self._port.readline().decode("ascii", "replace").strip()
        if not reply:
            raise ControllerError("no reply to %r (timeout)" % line)
        if reply.startswith("ERR"):
            raise ControllerError("%s: %s" % (line, reply))
        if reply != "OK" and not reply.startswith("OK "):
            raise ControllerError("unexpected reply to %r: %r" % (line, reply))
        return reply[2:].strip()

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
