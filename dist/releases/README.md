# Local release artifacts

These folders mirror GitHub Release assets when CI is unavailable or you prefer
building on your own machine.

| Folder | Contents |
| --- | --- |
| `v1.0.12/` | Windows MSI, NSIS setup, portable zip (after local build) |

Rebuild everything:

```powershell
.\scripts\package-local-release.ps1 -Tag v1.0.12
```

Skip rebuild and only re-copy existing `dist/installers/windows` artifacts:

```powershell
.\scripts\package-local-release.ps1 -Tag v1.0.12 -SkipBuild
```

End users on **macOS Apple Silicon** need the `*_aarch64.dmg` built on a Mac.
See `docs/INSTALL.md` and `scripts/macos_fixup_app.sh`.
