import threading

import pytest

from app.console import CommandLog


def test_ids_increment_and_never_repeat_after_overflow():
    log = CommandLog(maxlen=3)
    ids = [log.add("cmd", "x%d" % i) for i in range(5)]
    assert ids == [1, 2, 3, 4, 5]
    assert log.last_id == 5
    assert [e["id"] for e in log.since()] == [3, 4, 5]  # oldest dropped, ids keep counting


def test_since_returns_only_newer_entries_in_order():
    log = CommandLog()
    log.add("cmd", "ADVANCE 164")
    log.add("reply", "OK")
    log.add("event", "wind 10 steps")
    entries = log.since(1)
    assert [e["text"] for e in entries] == ["OK", "wind 10 steps"]
    assert set(entries[0]) == {"id", "t", "kind", "text"}
    assert isinstance(entries[0]["t"], float)
    assert log.since(3) == []


def test_maxlen_drops_oldest():
    log = CommandLog(maxlen=2)
    for t in "abc":
        log.add("event", t)
    assert [e["text"] for e in log.since()] == ["b", "c"]


def test_thread_safe():
    log = CommandLog(maxlen=1000)

    def go():
        for i in range(200):
            log.add("event", str(i))

    threads = [threading.Thread(target=go) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    ids = [e["id"] for e in log.since()]
    assert len(ids) == 400 and len(set(ids)) == 400


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        CommandLog().add("debug", "x")
