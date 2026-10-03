import os

def safe_name(name: str) -> str:
    base = os.path.basename(name.replace('\\', '/'))
    if base in ('', '.', '..'):
        raise ValueError('invalid filename')
    return base
