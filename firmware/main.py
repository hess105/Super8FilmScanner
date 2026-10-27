import sys
import time

from machine import PWM, Pin

import pins
from motion import step_delays_us
from protocol import ProtocolError, format_err, format_ok, parse_command

PULSE_US = 3  # TMC2209 needs >= 100 ns


class Motor:
    def __init__(self, step, direction, enable, hold):
        self.step = Pin(step, Pin.OUT, value=0)
        self.dir = Pin(direction, Pin.OUT, value=0)
        self.en = Pin(enable, Pin.OUT, value=1)  # TMC2209 EN is active low
        self.hold = hold

    def move(self, steps, rate):
        self.dir.value(1 if steps > 0 else 0)
        self.en.value(0)
        for delay in step_delays_us(steps, rate):
            self.step.value(1)
            time.sleep_us(PULSE_US)
            self.step.value(0)
            time.sleep_us(max(delay - PULSE_US, 1))
        if not self.hold:
            self.en.value(1)


film = Motor(pins.FILM_STEP, pins.FILM_DIR, pins.FILM_EN, hold=True)
reel = Motor(pins.REEL_STEP, pins.REEL_DIR, pins.REEL_EN, hold=False)

led = PWM(Pin(pins.LED_PWM))
led.freq(20000)  # above flicker and camera banding range
led.duty_u16(0)
light = 0


def set_light(percent):
    global light
    light = percent
    led.duty_u16(percent * 65535 // 100)


try:
    while True:
        line = sys.stdin.readline()
        if not line:
            continue  # EOF: do not parse an empty line
        try:
            cmd = parse_command(line)
            if cmd[0] == "ADVANCE":
                film.move(cmd[1], cmd[2])
                print(format_ok())
            elif cmd[0] == "WIND":
                reel.move(cmd[1], cmd[2])
                print(format_ok())
            elif cmd[0] == "LIGHT":
                set_light(cmd[1])
                print(format_ok())
            else:
                print(format_ok("light=%d" % light))
        except ProtocolError as e:
            print(format_err(str(e)))
        except Exception:
            print(format_err("internal"))
finally:  # leaving the loop (e.g. Ctrl-C, reflash) must not leave the LED lit or the drivers enabled
    led.duty_u16(0)
    film.en.value(1)
    reel.en.value(1)
