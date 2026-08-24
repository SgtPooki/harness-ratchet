"""Row transforms applied by the pipeline."""


def dedupe(rows):
    """Drop duplicate (name, amount) rows, preserving order."""
    seen = set()
    out = []
    for r in rows:
        key = (r["name"], r["amount"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def add_tax(rows, rate=0.1):
    """Return rows with a 'taxed' field added."""
    for r in rows:
        r["taxed"] = round(r["amount"] * (1 + rate), 2)
    return rows
