$ScriptDir = Split-Path -Parent -Path $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent -Path $ScriptDir

# Try both Windows and Unix virtual environment layouts
$PythonExe = Join-Path -Path $ProjectRoot -ChildPath ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = Join-Path -Path $ProjectRoot -ChildPath ".venv\bin\python"
}

$MainPy = Join-Path -Path $ProjectRoot -ChildPath "main.py"

if (-not (Test-Path $PythonExe)) {
    Write-Error "Missing Python executable at: $ProjectRoot\.venv\Scripts\python.exe or $ProjectRoot\.venv\bin\python"
    Write-Host "Create the .venv and install dependencies first."
    exit 1
}

& $PythonExe $MainPy $args
