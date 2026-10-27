from app.config import Settings


def test_defaults_keep_the_film_look():
    s = Settings()
    assert s.denoise is False
    assert s.resize_to is None
    assert s.steps_per_frame == 164


def test_missing_file_gives_defaults(tmp_path):
    assert Settings.load(tmp_path / "nope.json") == Settings()


def test_round_trip_and_unknown_keys(tmp_path):
    path = tmp_path / "scanner.json"
    s = Settings(steps_per_frame=170, resize_to=(3840, 2160))
    s.save(path)
    text = path.read_text().replace("{", '{"bogus": 1,', 1)
    path.write_text(text)
    loaded = Settings.load(path)
    assert loaded == s
    assert loaded.resize_to == (3840, 2160)
