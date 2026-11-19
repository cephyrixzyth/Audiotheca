"""Copy legacy feedback into the selected application home without replacing local decisions."""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

from api.paths import report_dir


def migrate(source: Path, destination: Path, *, apply: bool = False) -> list[dict]:
    if not source.is_dir() or source.resolve() == destination.resolve():
        raise ValueError("Select the old feedback directory, distinct from the destination")
    rows = []
    for path in sorted(source.iterdir()):
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in {".json", ".csv"}:
            continue
        dest = destination / path.name
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        try:
            if path.suffix == ".json" and not isinstance(json.loads(data), (dict, list)):
                raise ValueError("Expected a JSON object or array")
            if os.path.lexists(dest):
                state = "identical" if not dest.is_symlink() and dest.is_file() and dest.read_bytes() == data else "conflict"
            elif apply:
                destination.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=destination, delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temporary, dest)
                finally:
                    temporary.unlink(missing_ok=True)
                state = "copied"
            else:
                state = "available"
        except (ValueError, OSError, UnicodeError) as exc:
            rows.append({"file": path.name, "state": "error", "reason": str(exc)})
            continue
        rows.append({"file": path.name, "sha256": digest, "state": state})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Old dedupe_reports/feedback directory")
    parser.add_argument("--apply", action="store_true", help="Copy missing validated files into the current app home")
    args = parser.parse_args()
    rows = migrate(args.source, report_dir() / "feedback", apply=args.apply)
    print(json.dumps(rows, indent=2))
    return 1 if any(r["state"] in {"conflict", "error"} for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
