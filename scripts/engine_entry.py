"""PyInstaller entrypoint for the Audiotheca scan engine sidecar."""

from __future__ import annotations

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False) and not os.environ.get("AUDIOTHECA_HOME"):
    os.environ["AUDIOTHECA_HOME"] = str(Path(sys.executable).resolve().parent)

from cli import main  # noqa: E402


if __name__ == "__main__":
    main()
