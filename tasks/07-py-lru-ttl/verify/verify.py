import sys

sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else ".")
from ttlcache import TTLCache  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# --- LRU: get refreshes recency -------------------------------------------
clk = Clock()
c = TTLCache(2, clock=clk)
c.put("a", 1)
c.put("b", 2)
assert c.get("a") == 1  # a is now most recent
c.put("c", 3)  # must evict b (LRU), not a (FIFO)
assert c.get("a") == 1, "get() must refresh recency (evicted 'a' = FIFO bug)"
assert c.get("b", "gone") == "gone", "'b' should have been evicted"
assert c.get("c") == 3

# --- LRU: put-update refreshes recency ------------------------------------
clk = Clock()
c = TTLCache(2, clock=clk)
c.put("a", 1)
c.put("b", 2)
c.put("a", 10)  # update refreshes a
c.put("c", 3)  # evicts b
assert c.get("a") == 10, "put-update must refresh recency"
assert c.get("b", "gone") == "gone"

# --- TTL: expiry dead-ness --------------------------------------------------
clk = Clock()
c = TTLCache(3, clock=clk)
c.put("x", 1, ttl=5)
clk.t += 6
assert c.get("x", "dead") == "dead"
assert "x" not in c, "__contains__ must be False for expired entries"

# --- TTL: expired entries must not crowd out live ones ---------------------
clk = Clock()
c = TTLCache(2, clock=clk)
c.put("dead1", 1, ttl=1)
c.put("live", 2)
clk.t += 5  # dead1 expired
c.put("new", 3)  # capacity: expired dead1 must go, live must survive
assert c.get("live") == 2, "live entry evicted while an expired one existed"
assert c.get("new") == 3

# --- TTL: put resets the clock, get does not -------------------------------
clk = Clock()
c = TTLCache(2, clock=clk)
c.put("k", 1, ttl=10)
clk.t += 8
assert c.get("k") == 1
clk.t += 8  # 16s since write: get must NOT have extended the ttl
assert c.get("k", "dead") == "dead", "get() must not reset the TTL clock"
c.put("k2", 1, ttl=10)
clk.t += 8
c.put("k2", 2, ttl=10)  # rewrite resets clock
clk.t += 8
assert c.get("k2") == 2, "put() must reset the TTL clock"

# --- len() counts live entries only after access patterns ------------------
clk = Clock()
c = TTLCache(2, clock=clk)
c.put("p", 1, ttl=1)
clk.t += 2
c.put("q", 2)
c.put("r", 3)  # p is expired; q and r must both fit
assert c.get("q") == 2 and c.get("r") == 3, "expired entry consumed capacity"

# --- ttl=None never expires -------------------------------------------------
clk = Clock()
c = TTLCache(1, clock=clk)
c.put("forever", 1)
clk.t += 10**9
assert c.get("forever") == 1

print("PASS")
