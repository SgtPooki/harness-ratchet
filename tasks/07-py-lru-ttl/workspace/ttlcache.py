"""A size-bounded LRU cache with optional per-entry TTL.

Contract:
- Capacity is a hard bound: the cache never holds more than `capacity` live
  entries.
- Eviction is strictly least-recently-USED: both `get` hits and `put` updates
  refresh an entry's recency.
- An entry with a TTL expires `ttl` seconds after it was last WRITTEN (puts
  reset the clock; gets do not).
- Expired entries are dead: `get` returns the default, `__contains__` is False,
  and an expired entry must not count toward capacity nor be preferred for
  survival over live entries.
- `ttl=None` means the entry never expires.
"""

import time


class TTLCache:
    def __init__(self, capacity, clock=time.monotonic):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self._clock = clock
        self._data = {}  # key -> (value, expires_at or None)

    def put(self, key, value, ttl=None):
        """Insert or update an entry, refreshing its recency and TTL clock."""
        expires = self._clock() + ttl if ttl is not None else None
        if key not in self._data and len(self._data) >= self.capacity:
            oldest = next(iter(self._data))
            del self._data[oldest]
        self._data[key] = (value, expires)

    def get(self, key, default=None):
        """Return the live value for key (refreshing recency), else default."""
        if key not in self._data:
            return default
        value, expires = self._data[key]
        if expires is not None and self._clock() >= expires:
            return default
        return value

    def __contains__(self, key):
        return key in self._data

    def __len__(self):
        return len(self._data)
