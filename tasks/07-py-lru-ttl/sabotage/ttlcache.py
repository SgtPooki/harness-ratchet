"""Sabotage: partial fix — LRU recency fixed, TTL/expiry contract still broken."""

import time
from collections import OrderedDict


class TTLCache:
    def __init__(self, capacity, clock=time.monotonic):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self._clock = clock
        self._data = OrderedDict()

    def put(self, key, value, ttl=None):
        expires = self._clock() + ttl if ttl is not None else None
        if key in self._data:
            del self._data[key]
        elif len(self._data) >= self.capacity:
            self._data.popitem(last=False)
        self._data[key] = (value, expires)

    def get(self, key, default=None):
        if key not in self._data:
            return default
        value, expires = self._data[key]
        if expires is not None and self._clock() >= expires:
            return default
        self._data.move_to_end(key)
        return value

    def __contains__(self, key):
        return key in self._data

    def __len__(self):
        return len(self._data)
