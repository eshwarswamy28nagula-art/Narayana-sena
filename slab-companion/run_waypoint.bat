@echo off
setlocal
cd /d "%~dp0"
echo Installing required Python packages...
py -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed.
  pause
  exit /b 1
)
echo.
echo Starting Waypoint at http://127.0.0.1:5050
start "Waypoint browser" http://127.0.0.1:5050
py app.py
pause
