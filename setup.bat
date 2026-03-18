@echo off
echo === JAV Downloader Setup ===
echo.

REM Always recreate venv to fix broken paths (e.g. after moving the folder)
echo Recreating virtual environment...
if exist "venv" rmdir /s /q venv
python -m venv venv

echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo Installing Python dependencies...
pip install -r requirements.txt

echo.
echo === Setup complete! Run run.bat to start the app. ===
echo NOTE: nodriver will automatically download and manage Chrome on first run.
pause
