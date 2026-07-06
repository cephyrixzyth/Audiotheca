"""K-DET: root key detection from filename patterns."""



from __future__ import annotations



import re

from typing import Any



_KEY_RE = re.compile(r"\b([A-G](?:#|b)?)\s*(?:maj|min|major|minor|m)?\b", re.I)

_KEY_IN_NAME = re.compile(
    r"(?i)key[_-]([A-G](?:#|b)?)(?:[_-]?(maj|min|major|minor|m)|(?:maj|min|major|minor|m))?",
)





def detect_key(name: str) -> dict[str, Any]:

    inline = _KEY_IN_NAME.search(name)

    if inline:

        key = inline.group(1).upper()

        mode_raw = (inline.group(2) or "").lower()

        mode = "minor" if mode_raw in {"min", "minor", "m"} else "major" if mode_raw else "unknown"

        return {

            "name": name,

            "key": key,

            "mode": mode,

            "confidence": "high",

            "source": "filename",

        }



    match = _KEY_RE.search(name)

    key = match.group(1).upper() if match else None

    return {

        "name": name,

        "key": key,

        "mode": "unknown",

        "confidence": "medium" if key else "none",

        "source": "filename" if key else None,

    }

