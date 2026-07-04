"""Contextual AI lookup — fallback identification when local heuristics fail."""

from audiotheca.ai_lookup.engine import LookupEngine, needs_ai_lookup, queue_ai_lookups
from audiotheca.ai_lookup.disambiguation import LookupResult

__all__ = ["LookupEngine", "LookupResult", "needs_ai_lookup", "queue_ai_lookups"]
