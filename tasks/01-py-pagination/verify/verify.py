import sys

sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else ".")
from paginate import paginate, total_pages  # noqa: E402

items = list(range(10))
assert paginate(items, 1, 3) == [0, 1, 2], "page 1 wrong"
assert paginate(items, 2, 3) == [3, 4, 5], "page 2 wrong"
assert paginate(items, 4, 3) == [9], "last partial page wrong"
assert paginate(items, 5, 3) == [], "past-end page should be []"
assert paginate([], 1, 3) == [], "empty list page 1"
assert paginate(items, 1, 10) == items, "exact single page"
assert paginate(items, 2, 10) == [], "page 2 of single-page list"

assert total_pages(items, 3) == 4, "10/3 -> 4 pages"
assert total_pages(items, 5) == 2, "10/5 -> 2 pages"
assert total_pages(items, 10) == 1
assert total_pages(items, 11) == 1, "10 items, per_page 11 -> 1 page"
assert total_pages([], 3) == 0

for bad in ((items, 0, 3), (items, 1, 0)):
    try:
        paginate(*bad)
        raise SystemExit("expected ValueError for %r" % (bad,))
    except ValueError:
        pass

try:
    total_pages(items, 0)
    raise SystemExit("expected ValueError for per_page=0")
except ValueError:
    pass

print("PASS")
