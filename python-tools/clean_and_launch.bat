@echo off
REM Clean & Launch Chrome - double-click this file
REM Closes Chrome, cleans up the saved-tab-group bloat, relaunches Chrome cleanly.
cd /d "%~dp0"
python clean_and_launch_chrome.py
echo.
echo Press any key to close...
pause >nul
