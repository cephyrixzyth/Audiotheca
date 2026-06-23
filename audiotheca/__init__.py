"""Audiotheca — audio library dedupe and routing engine."""

from audiotheca.config import CACHE_SCHEMA, DRY_RUN, ENGINE_VERSION, ROOT_DIR
from audiotheca.engine import DeduplicationEngine

__all__ = [
    "CACHE_SCHEMA",
    "DRY_RUN",
    "DeduplicationEngine",
    "ENGINE_VERSION",
    "ROOT_DIR",
]
