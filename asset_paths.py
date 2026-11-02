"""Validate site assets, including the established local research-library links."""
from pathlib import Path


def is_local_asset(root, path):
    """Require an assets entry backed by this project or its research library.

    The source website keeps some large files in the adjacent archive. Only
    references starting inside this project's assets tree may follow those links.
    """
    root = Path(root).absolute()
    resolved_root = root.resolve()
    path = Path(path)
    if '..' in path.parts:
        return False
    if not path.is_absolute():
        path = root / path
    assets = resolved_root / 'assets'
    if not (path.is_relative_to(root / 'assets') or path.is_relative_to(assets)):
        return False
    try:
        resolved = path.resolve(strict=True)
        return (resolved.is_file() and
                (resolved.is_relative_to(assets) or
                 resolved.is_relative_to(resolved_root.parent / 'Aguri_Research_Library')))
    except (OSError, RuntimeError):
        return False
