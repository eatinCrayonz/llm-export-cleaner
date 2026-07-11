# Windows Application

Build from the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-windows.ps1
```

The build produces:

```text
dist\windows\LLMExportCleaner-Windows.zip
```

Extract it and run `Install.cmd`. The installer copies application files to
`%LOCALAPPDATA%\Programs\LLM Export Cleaner`, creates Desktop and Start Menu
shortcuts, and launches the app. Reinstallation preserves the separate SQLite
library under `%LOCALAPPDATA%\LLM Export Cleaner`.

The ZIP contains application code only. Raw exports, cleaned outputs, and
populated databases must never be placed under `dist`.

