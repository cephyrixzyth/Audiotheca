"""
Audiotheca engine entry point (backward-compatible shim).

Prefer: python -m audiotheca scan  or  python cli.py scan
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
    import sys

    from audiotheca.cli import main

    main(["scan", *sys.argv[1:]])
