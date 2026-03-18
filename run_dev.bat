@echo off
setlocal
set "SCRIPT_DIR=%~dp0"

echo Checking for existing app process...
set "FOUND_STALE="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$scriptDir = [System.IO.Path]::GetFullPath('%SCRIPT_DIR%'); Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -match 'main\.py' -and $_.CommandLine -like ('*' + $scriptDir + '*') } | ForEach-Object { $_.ProcessId }"`) do (
    set "FOUND_STALE=1"
    echo Stopping stale PID %%P
    taskkill /PID %%P /F >nul 2>&1
)
if not defined FOUND_STALE echo No stale app process found.

if not exist "venv\Scripts\activate.bat" (
    echo Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
set "JAV_DEV_RELOAD=1"
python main.py
pause