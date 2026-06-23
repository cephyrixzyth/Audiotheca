"""Audiotheca — audio library dedupe and routing engine."""

from audiotheca.config import CACHE_SCHEMA, DRY_RUN, ENGINE_VERSION, ROOT_DIR
from audiotheca.engine import DeduplicationEngine
from audiotheca.vendor_overrides import compile_user_routes, load_user_vendors, match_keyword

__all__ = [
    "CACHE_SCHEMA",
    "DRY_RUN",
    "DeduplicationEngine",
    "ENGINE_VERSION",
    "ROOT_DIR",
    "compile_user_routes",
    "load_user_vendors",
    "match_keyword",
]
