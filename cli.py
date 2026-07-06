"""Backward-compatible CLI shim — prefer python -m audiotheca."""

from audiotheca.cli import build_parser, main

__all__ = ["build_parser", "main"]

if __name__ == "__main__":
    main()
