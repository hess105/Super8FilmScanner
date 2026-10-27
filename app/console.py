import itertools
import threading
import time
from collections import deque

KINDS = ("cmd", "reply", "event", "error")


class CommandLog:
    """Recent controller traffic and scan events for the page's terminal."""

    def __init__(self, maxlen=500):
        self._entries = deque(maxlen=maxlen)
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._last_id = 0

    def add(self, kind, text):
        if kind not in KINDS:
            raise ValueError("unknown kind %r" % kind)
        with self._lock:
            self._last_id = next(self._ids)
            self._entries.append({"id": self._last_id, "t": time.time(), "kind": kind, "text": str(text)})
            return self._last_id

    def since(self, last_id=0):
        with self._lock:
            return [dict(e) for e in self._entries if e["id"] > last_id]

    @property
    def last_id(self):
        return self._last_id
