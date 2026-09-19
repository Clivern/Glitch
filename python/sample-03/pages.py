HEADER_PAGE = 0
FIRST_DATA_PAGE = 1


def load_page(page_id: int) -> bytes:
    """Load a user data page from the file.

    Page 0 is the on-disk header. The decoder panics if it is asked to
    treat that page as row data.
    """
    if page_id == HEADER_PAGE:
        raise RuntimeError("panic: page 0 is the file header, not a data page")
    return f"page:{page_id}".encode()
