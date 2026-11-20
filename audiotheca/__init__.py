"""Audiotheca — audio library dedupe and routing engine."""

from audiotheca.config import CACHE_SCHEMA, DRY_RUN, ENGINE_VERSION, ROOT_DIR

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


def __getattr__(name):
    if name == "DeduplicationEngine":
        from audiotheca.engine import DeduplicationEngine
        return DeduplicationEngine
    if name in {"compile_user_routes", "load_user_vendors", "match_keyword"}:
        from audiotheca import vendor_overrides
        return getattr(vendor_overrides, name)
    raise AttributeError(name)
