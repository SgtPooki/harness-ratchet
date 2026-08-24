from ttlcache import TTLCache

c = TTLCache(2)
c.put("a", 1)
c.put("b", 2)
assert c.get("a") == 1
assert c.get("b") == 2
c.put("c", 3)
assert len(c) == 2
print("smoke ok")
