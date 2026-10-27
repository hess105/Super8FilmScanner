import math


def wind_steps(frames_on_spool, frames_to_add, settings):
    """Motor steps to take up `frames_to_add` frames, given how much film is already on the spool."""
    core_radius = settings.spool_inner_diameter_mm / 2
    tape_length = settings.frame_height_mm * frames_on_spool
    spool_radius = math.sqrt(tape_length * settings.film_thickness_mm / math.pi + core_radius ** 2)
    arc_length = frames_to_add * settings.frame_height_mm
    revolutions = arc_length / (2 * math.pi * spool_radius)
    return round(revolutions * settings.reel_steps_per_rev)
