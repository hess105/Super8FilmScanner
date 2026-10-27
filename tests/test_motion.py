from motion import START_RATE, step_delays_us


def test_zero_steps_yields_nothing():
    assert list(step_delays_us(0, 2000)) == []


def test_one_delay_per_step_and_sign_ignored():
    assert len(list(step_delays_us(164, 2000))) == 164
    assert len(list(step_delays_us(-164, 2000))) == 164


def test_ramp_is_symmetric_and_starts_slow():
    delays = list(step_delays_us(164, 2000))
    assert delays == delays[::-1]
    assert delays[0] == 1000000 // START_RATE


def test_long_move_cruises_at_rate_but_never_faster():
    delays = list(step_delays_us(1000, 2000))
    assert min(delays) == 500
    assert delays[500] == 500


def test_rate_below_start_rate_is_respected():
    assert min(step_delays_us(50, 170)) >= 1000000 // 170
