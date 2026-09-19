from pages import load_page


def export_from_start() -> bytes:
    """Dump the file from the beginning."""
    return load_page(1)
