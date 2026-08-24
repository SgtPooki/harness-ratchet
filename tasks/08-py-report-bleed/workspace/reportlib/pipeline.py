"""Report assembly."""

from .loader import load_rows
from .transforms import add_tax, dedupe


def collect_sources(sources, rows=[]):
    """Load and accumulate rows from every (name, lines) source pair."""
    for source_name, raw_lines in sources:
        rows.extend(load_rows(source_name, raw_lines))
    return rows


def build_report(title, sources):
    """Build a report dict from (name, lines) source pairs."""
    rows = collect_sources(sources)
    rows = dedupe(rows)
    rows = add_tax(rows)
    total = round(sum(r["taxed"] for r in rows), 2)
    return {"title": title, "rows": rows, "total": total}
