@echo off
echo === JAV Video System - Build Executable ===
echo.

if not exist "venv\Scripts\activate.bat" (
    echo Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat

REM Install PyInstaller into venv if missing
pip install pyinstaller --quiet

REM --- Pre-build cleanup ---------------------------------------------------
echo Cleaning previous build artefacts...
if exist build    rd /s /q build
if exist dist     rd /s /q dist
if exist setup    rd /s /q setup
if exist .nicegui rd /s /q .nicegui

REM Remove __pycache__ dirs so they are not copied into dist via --add-data
for /d /r scraper    %%d in (__pycache__) do if exist "%%d" rd /s /q "%%d"
for /d /r translator %%d in (__pycache__) do if exist "%%d" rd /s /q "%%d"
for /d /r utils      %%d in (__pycache__) do if exist "%%d" rd /s /q "%%d"
if exist __pycache__ rd /s /q __pycache__
echo.
REM -------------------------------------------------------------------------

echo Building with PyInstaller (--onedir mode)...
echo.

pyinstaller ^
    --name "JAV Video System" ^
    --noconfirm ^
    --windowed ^
    --icon NONE ^
    --add-data "scraper;scraper" ^
    --add-data "translator;translator" ^
    --add-data "utils;utils" ^
    --hidden-import "nicegui" ^
    --hidden-import "nicegui.elements" ^
    --hidden-import "nicegui.storage" ^
    --hidden-import "openai" ^
    --hidden-import "nodriver" ^
    --hidden-import "curl_cffi" ^
    --hidden-import "bs4" ^
    --hidden-import "httpx" ^
    --collect-all "nicegui" ^
    main.py

if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller failed.
    pause
    exit /b 1
)

set "DIST_DIR=dist\JAV Video System"

REM --- Copy nodriver Chrome for Testing binaries ---------------------------
echo.
echo Locating nodriver Chrome for Testing binaries...
set "ND_SRC=%LOCALAPPDATA%\nodriver"
if not exist "%ND_SRC%" set "ND_SRC=%USERPROFILE%\.local\share\nodriver"

if exist "%ND_SRC%" (
    echo Copying Chrome binaries from %ND_SRC% ...
    xcopy /E /I /Y "%ND_SRC%" "%DIST_DIR%\nodriver\"
    echo.
) else (
    echo NOTE: nodriver Chrome binaries not found.
    echo       The app will download Chrome for Testing on first run.
)

REM --- Copy browser extension ----------------------------------------------
echo Copying browser extension...
xcopy /E /I /Y "extension" "%DIST_DIR%\extension\"
echo.

REM --- Inno Setup ----------------------------------------------------------
echo Building installer with Inno Setup...
set "ISCC=C:\ProgramData\chocolatey\bin\ISCC.exe"
if not exist "%ISCC%" (
    REM Fallback to standard install paths
    if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
)
if not exist "%ISCC%" (
    echo ERROR: Inno Setup compiler not found.
    echo        Install it from https://jrsoftware.org/isdl.php or via:  choco install innosetup
    pause
    exit /b 1
)

"%ISCC%" installer.iss
if errorlevel 1 (
    echo.
    echo ERROR: Inno Setup compilation failed.
    pause
    exit /b 1
)
REM -------------------------------------------------------------------------
echo.
echo === Build complete! ===
echo.
echo   Installer:  setup\JAV Video System Setup.exe
echo   Raw folder: %DIST_DIR%\   (for testing without installing)
echo.
echo   The installer will:
echo     - Install to %%LOCALAPPDATA%%\Programs\JAV Video System  (no UAC needed)
echo     - Add a Start Menu entry
echo     - Offer an optional desktop shortcut
echo     - Register an uninstaller in Add/Remove Programs
echo.
echo   App data lives in: %APPDATA%\JAV Video System
echo   Existing installs in: %APPDATA%\JAV Downloader continue to work automatically.
echo   To change it: use Settings inside the app.
echo.
pause
