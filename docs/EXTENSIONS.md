# Extensions

Extensions let you add vendor routing rules, notification channels and run exporters without waiting for a release. They are plain Python files, so they run with Audiotheca's own permissions. Loading is **off** by default.

## Turning extensions on

1. Create the folder `<AUDIOTHECA_HOME>/extensions/` (or point `AUDIOTHECA_EXTENSIONS_DIR` at another folder).
2. Put one or more `.py` files in it. File names may use letters, digits, `_` and `-`.
3. Start Audiotheca with `AUDIOTHECA_EXTENSIONS=1`.

System → Automation → Extensions lists every loaded extension, what it provides, and any load errors. The API can list and run extensions but never writes extension files.

## What an extension can define

| Name | Type | Effect |
| --- | --- | --- |
| `NAME` | `str` | Display name in the Extensions view (defaults to the file name) |
| `VENDOR_RULES` | `dict[str, list[str]]` | Company name to keywords. Merged into vendor routing with strong priority |
| `notify(title, body)` | function | Called after the built-in notification targets on every notification |
| `export_run(stamp, items)` | function returning `(filename, text)` | Adds an export for a run. `items` are the normalized scan rows (`section`, `item_name`, `path`, `vendor`, `version_key`, `size_mb`, `status`, …) |
| `embed_audio(path)` | function returning a list of floats | Audio embedding for the sample finder (for example a CLAP model you install). When present, the index stores these vectors and ranks by them instead of the built-in spectral features. Changing or removing the embedder re-analyses the index on the next run. Only the first extension with `embed_audio` is used |

An exception in one extension is caught and reported. It does not stop the scan or other extensions.

## Example

```python
# extensions/studio.py
import json
import urllib.request

NAME = "Studio rules"

VENDOR_RULES = {
    "Acme Audio": ["acme", "acmesynth"],
}

def notify(title: str, body: str) -> None:
    req = urllib.request.Request(
        "https://chat.example.com/hooks/audiotheca",
        data=json.dumps({"text": f"{title}\n{body}"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=10)

def export_run(stamp: str, items: list[dict]) -> tuple[str, str]:
    lines = ["vendor,name,size_mb"]
    lines += [f'{i["vendor"]},{i["item_name"]},{i["size_mb"]}' for i in items]
    return f"vendor_sizes_{stamp}.csv", "\n".join(lines)
```

The air-gap setting does not reach inside extension code. An extension that makes network calls does so on its own.
