$ErrorActionPreference = "Stop"
$Source = $PSScriptRoot
$InstallRoot = Join-Path $env:LOCALAPPDATA "Programs\LLM Export Cleaner"
$Executable = Join-Path $InstallRoot "LLMExportCleaner.exe"

if (Get-Process -Name "LLMExportCleaner" -ErrorAction SilentlyContinue) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        "Close LLM Export Cleaner, then run Install.cmd again.",
        "LLM Export Cleaner is running", "OK", "Information"
    ) | Out-Null
    exit 1
}

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
Copy-Item -Path (Join-Path $Source "*") -Destination $InstallRoot -Recurse -Force

$Shell = New-Object -ComObject WScript.Shell
$Desktop = Join-Path $env:USERPROFILE "Desktop"
$StartMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
foreach ($Folder in @($Desktop, $StartMenu)) {
    $Shortcut = $Shell.CreateShortcut((Join-Path $Folder "LLM Export Cleaner.lnk"))
    $Shortcut.TargetPath = $Executable
    $Shortcut.WorkingDirectory = $InstallRoot
    $Shortcut.IconLocation = "$Executable,0"
    $Shortcut.Description = "Clean, filter, search, and export LLM conversations"
    $Shortcut.Save()
}
Start-Process -FilePath $Executable

