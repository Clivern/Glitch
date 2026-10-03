def safe_list(items):
    """Return items or an empty list — never crash on None."""
    return list(items or [])
