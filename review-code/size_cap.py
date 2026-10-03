MAX_BYTES = 1_000_000

def capped_read(data: bytes) -> bytes:
    return data[:MAX_BYTES]
