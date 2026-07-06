; Kill running Audiotheca and PyInstaller sidecars before upgrade/reinstall.
; Without this, NSIS fails with "error opening file for writing" when sidecars stay locked.

!macro _audiotheca_kill name
  nsExec::ExecToLog 'taskkill /F /T /IM "${name}"'
  Pop $0
!macroend

!macro NSIS_HOOK_PREINSTALL
  !insertmacro _audiotheca_kill "Audiotheca.exe"
  !insertmacro _audiotheca_kill "api-server.exe"
  !insertmacro _audiotheca_kill "audiotheca-engine.exe"
  ; Triple-suffixed sidecar names from older bundles
  !insertmacro _audiotheca_kill "api-server-x86_64-pc-windows-msvc.exe"
  !insertmacro _audiotheca_kill "audiotheca-engine-x86_64-pc-windows-msvc.exe"
  Sleep 2000
  ; Force replace unversioned PyInstaller exes (NSIS may skip locked/stale copies)
  Delete "$INSTDIR\api-server.exe"
  Delete "$INSTDIR\audiotheca-engine.exe"
  Delete "$INSTDIR\binaries\api-server.exe"
  Delete "$INSTDIR\binaries\audiotheca-engine.exe"
  Delete "$INSTDIR\resources\api-server.exe"
  Delete "$INSTDIR\resources\audiotheca-engine.exe"
  Delete "$INSTDIR\resources\api-server-x86_64-pc-windows-msvc.exe"
  Delete "$INSTDIR\resources\audiotheca-engine-x86_64-pc-windows-msvc.exe"
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  !insertmacro _audiotheca_kill "Audiotheca.exe"
  !insertmacro _audiotheca_kill "api-server.exe"
  !insertmacro _audiotheca_kill "audiotheca-engine.exe"
  !insertmacro _audiotheca_kill "api-server-x86_64-pc-windows-msvc.exe"
  !insertmacro _audiotheca_kill "audiotheca-engine-x86_64-pc-windows-msvc.exe"
  Sleep 2000
!macroend
