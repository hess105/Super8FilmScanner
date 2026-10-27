import re


class ControllerError(Exception):
    pass


COMMANDS = ("ADVANCE", "WIND", "LIGHT", "STATUS")
MAX_COMMAND = 40
INT_RE = re.compile(r"^-?\d+$")
DEFAULT_RATE = {"ADVANCE": 2000, "WIND": 1500}
MAX_STEPS, MAX_RATE, MAX_MOVE_S = 20000, 4000, 15  # the firmware cannot abort a move


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
        try:
            self._port.reset_input_buffer()
            self._port.write((line + "\n").encode("ascii"))
            reply = self._port.readline().decode("ascii", "replace").strip()
        except OSError as e:  # pyserial's SerialException is an OSError (USB unplugged)
            self._fail("%s: %s" % (line, e))
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
        name, args = parts[0].upper(), parts[1:]
        if not all(INT_RE.match(a) for a in args):
            raise ValueError("%s arguments must be plain integers" % name)
        nums = [int(a) for a in args]
        if name == "STATUS" and nums:
            raise ValueError("STATUS takes no arguments")
        if name == "LIGHT" and (len(nums) != 1 or not 0 <= nums[0] <= 100):
            raise ValueError("LIGHT takes one percent, 0-100")
        if name in DEFAULT_RATE:
            if len(nums) not in (1, 2):
                raise ValueError("%s takes steps and an optional rate" % name)
            steps, rate = nums[0], nums[1] if len(nums) == 2 else DEFAULT_RATE[name]
            if not 1 <= rate <= MAX_RATE:
                raise ValueError("rate must be 1-%d steps/s" % MAX_RATE)
            if abs(steps) > MAX_STEPS or abs(steps) / rate > MAX_MOVE_S:
                raise ValueError("move too long: at most %d steps and %d s" % (MAX_STEPS, MAX_MOVE_S))
        return self._send(" ".join([name] + args))

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
