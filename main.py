"""
Audiotheca engine entry point (backward-compatible shim).

Prefer: python cli.py  or  python -m audiotheca (future)
Engine implementation lives in audiotheca.engine; config in audiotheca.config.
"""

from audiotheca.config import *  # noqa: F403
from audiotheca.engine import DeduplicationEngine
from audiotheca.helpers import _archive_stem, _limit_walk, _squash, _walk_depth

__all__ = [
    "DeduplicationEngine",
    "_archive_stem",
    "_limit_walk",
    "_squash",
    "_walk_depth",
]

if __name__ == "__main__":
    from cli import main

    main()
