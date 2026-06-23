"""Optional third-party dependencies shared across engine mixins."""

from __future__ import annotations

try:
    import pefile

    HAS_PEFILE = True
except ImportError:
    HAS_PEFILE = False
    pefile = None

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

try:
    from rapidfuzz import fuzz

    HAS_FUZZ = True
except ImportError:
    HAS_FUZZ = False
    fuzz = None
