"""Row loading with a parse cache keyed by source name."""

_PARSE_CACHE = {}


def load_rows(source_name, raw_lines, cache=_PARSE_CACHE):
    """Parse 'name,amount' lines into row dicts, caching by source name."""
    if source_name in cache:
        return cache[source_name]
    rows = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        name, _, amount = line.partition(",")
        rows.append({"name": name.strip(), "amount": float(amount)})
    cache[source_name] = rows
    return rows
