"""Simple pagination helpers.

Pages are 1-based: page 1 is the first page.
"""


def paginate(items, page, per_page):
    """Return the items on the given 1-based page.

    Raises ValueError if page < 1 or per_page < 1.
    Returns [] for pages past the end.
    """
    if page < 1 or per_page < 1:
        raise ValueError("page and per_page must be >= 1")
    start = page * per_page
    end = start + per_page
    return items[start:end]


def total_pages(items, per_page):
    """Return how many 1-based pages exist for this list.

    An empty list has 0 pages. Raises ValueError if per_page < 1.
    """
    if per_page < 1:
        raise ValueError("per_page must be >= 1")
    return len(items) // per_page
