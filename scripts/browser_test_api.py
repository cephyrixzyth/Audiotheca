"""Start a loopback API with bundled reports and a throwaway copy of the demo library."""
import os
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
if __name__ == "__main__":
    with TemporaryDirectory(prefix="audiotheca-browser-") as tmp:
        home = Path(tmp)
        shutil.copytree(root / "docs/demo/reports", home / "dedupe_reports")
        library = home / "library"
        shutil.copytree(root / "docs/demo/library", library)
        os.environ.update(AUDIOTHECA_HOME=tmp, AUDIOTHECA_LIBRARY_ROOT=str(library),
                          AUDIOTHECA_LIBRARY_ROOTS=str(library), AUDIOTHECA_NO_RELOAD="1")
        from api.server import main
        main()
