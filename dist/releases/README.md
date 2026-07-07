# Local release artifacts

Mirror GitHub Release assets when Actions quota is exhausted.

| Platform | Build command | Output |
| --- | --- | --- |
| **Windows** | `.\scripts\package-local-release.ps1 -Tag v1.0.12` | `dist/installers/windows/` |
| **Linux** | `.\scripts\build-linux-docker.ps1` | `dist/installers/linux/` |
| **macOS** | `./scripts/build-release-mac.sh --both` (on a Mac) | `dist/installers/mac/` |

Stage everything into one folder:

```powershell
.\scripts\stage-local-release.ps1 -Tag v1.0.12 -Merge
```

**macOS DMGs cannot be built on Windows.** On your M4 Mac:

```bash
git pull
chmod +x scripts/build-release-mac.sh scripts/macos_fixup_app.sh
./scripts/build-release-mac.sh --both
```

Copy `dist/installers/mac/*.dmg` back to this PC (or re-run stage on the Mac).
