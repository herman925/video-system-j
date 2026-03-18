@echo off
if not exist "venv\Scripts\activate.bat" (
    echo Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)
call venv\Scripts\activate.bat
echo Starting Tracker Effects Lab...
python run_lab.py
pause