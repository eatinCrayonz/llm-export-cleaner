param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildRoot = Join-Path $RepoRoot "build\windows"
$Venv = Join-Path $BuildRoot "venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$DistRoot = Join-Path $RepoRoot "dist\windows"
$AppFolder = Join-Path $DistRoot "LLMExportCleaner"

New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
$ProvidedPython = Resolve-Path $Python -ErrorAction SilentlyContinue
if ($ProvidedPython) {
    & $ProvidedPython.Path -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $VenvPython = $ProvidedPython.Path
        $Venv = Split-Path (Split-Path $VenvPython -Parent) -Parent
    }
}
if (-not (Test-Path $VenvPython)) { & $Python -m venv $Venv }
& $VenvPython -m pip install --no-build-isolation -e $RepoRoot pyinstaller
if ($LASTEXITCODE -ne 0) { throw "Unable to install build dependencies." }

$Config = Get-Content (Join-Path $Venv "pyvenv.cfg")
$HomeLine = $Config | Where-Object { $_ -like "home = *" } | Select-Object -First 1
$PythonHome = if ($HomeLine) { $HomeLine.Substring("home = ".Length).Trim() } else { Split-Path (Split-Path $VenvPython -Parent) -Parent }
$env:TCL_LIBRARY = Join-Path $PythonHome "tcl\tcl8.6"
$env:TK_LIBRARY = Join-Path $PythonHome "tcl\tk8.6"

& $VenvPython -m PyInstaller --noconfirm --clean --windowed --onedir `
    --name LLMExportCleaner --distpath $DistRoot `
    --workpath (Join-Path $BuildRoot "pyinstaller") --specpath $BuildRoot `
    (Join-Path $RepoRoot "src\llm_export_cleaner\desktop.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

$Internal = Join-Path $AppFolder "_internal"
foreach ($Directory in @((Join-Path $Internal "tkinter"), (Join-Path $Internal "_tcl_data"), (Join-Path $Internal "_tk_data"))) {
    New-Item -ItemType Directory -Force -Path $Directory | Out-Null
}
Copy-Item (Join-Path $PythonHome "Lib\tkinter\*") (Join-Path $Internal "tkinter") -Recurse -Force
Copy-Item (Join-Path $PythonHome "tcl\tcl8.6\*") (Join-Path $Internal "_tcl_data") -Recurse -Force
Copy-Item (Join-Path $PythonHome "tcl\tk8.6\*") (Join-Path $Internal "_tk_data") -Recurse -Force
foreach ($Runtime in @("_tkinter.pyd", "tcl86t.dll", "tk86t.dll")) { Copy-Item (Join-Path $PythonHome "DLLs\$Runtime") $Internal -Force }
Copy-Item (Join-Path $PSScriptRoot "Install.ps1") $AppFolder -Force
Copy-Item (Join-Path $PSScriptRoot "Install.cmd") $AppFolder -Force

$Archive = Join-Path $DistRoot "LLMExportCleaner-Windows.zip"
if (Test-Path $Archive) { Remove-Item -LiteralPath $Archive -Force }
Compress-Archive -Path $AppFolder -DestinationPath $Archive -CompressionLevel Optimal
Write-Host "Standalone package: $Archive"
