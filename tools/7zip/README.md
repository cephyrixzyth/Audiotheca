# Bundled 7-Zip (optional)

Audiotheca lists archive contents (`.rar`, `.7z`, `.iso`, …) without extracting. The engine looks here **before** a system install:

| Platform | Expected path |
|----------|----------------|
| Windows | `tools/7zip/win64/7z.exe` |
| Linux | `tools/7zip/linux/7zz` or `7z` |
| macOS | `tools/7zip/mac/7zz` |

## Setup

From the repo root:

```powershell
.\scripts\setup_7zip.ps1
```

Or download [7-Zip Extra](https://www.7-zip.org/download.html) / standalone `7zz` and place binaries in the folders above.

Override location with `AUDIOTHECA_HOME\tools\7zip`.

When bundled 7-Zip is present, the API health check reports `archive_tool` and archive peek avoids `NEEDS_7ZIP` verdicts.
