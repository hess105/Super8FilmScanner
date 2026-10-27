import math

START_RATE = 200  # steps per second at the start and end of every move


def step_delays_us(steps, rate, accel=8000):
    """Microseconds between steps for a trapezoid speed profile."""
    steps = abs(steps)
    for i in range(steps):
        d = min(i, steps - 1 - i)  # steps from the nearest end of the move
        v = min(rate, math.sqrt(START_RATE * START_RATE + 2 * accel * d))
        yield int(1000000 / v)
