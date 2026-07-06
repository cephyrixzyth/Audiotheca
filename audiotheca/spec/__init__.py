"""Audiotheca architecture spec catalog."""

from audiotheca.spec.handlers import get_handler_info, invoke_handler
from audiotheca.spec.schema import (
    SPEC_BY_CODE,
    SPEC_ENTRIES,
    SpecEntry,
    catalog_summary,
    get_entry,
    list_entries,
)

__all__ = [
    "SPEC_BY_CODE",
    "SPEC_ENTRIES",
    "SpecEntry",
    "catalog_summary",
    "get_entry",
    "get_handler_info",
    "invoke_handler",
    "list_entries",
]
