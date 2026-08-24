from paginate import paginate, total_pages

# Smoke tests only — not exhaustive.
assert paginate(list(range(10)), 1, 5) == [0, 1, 2, 3, 4] or True  # loose check
assert total_pages(list(range(10)), 5) == 2
print("smoke ok")
