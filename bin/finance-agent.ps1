$ScriptDir = Split-Path -Parent -Path $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent -Path $ScriptDir
$PythonExe = Join-Path -Path $ProjectRoot -ChildPath ".venv\Scripts\python.exe"
$MainPy = Join-Path -Path $ProjectRoot -ChildPath "main.py"

if (-not (Test-Path $PythonExe)) {
    Write-Error "Missing Python executable at: $PythonExe"
    Write-Host "Create the .venv and install dependencies first."
    exit 1
}

& $PythonExe $MainPy $args
