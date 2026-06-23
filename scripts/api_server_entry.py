"""PyInstaller entrypoint for the Audiotheca API sidecar."""

from __future__ import annotations

import os

os.environ.setdefault("AUDIOTHECA_NO_RELOAD", "1")

from api.server import main  # noqa: E402

if __name__ == "__main__":
    main()
