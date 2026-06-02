@echo off
REM Clean & Launch Chrome (KEEP ONE SET) - double-click this file
REM Keeps one group per name, removes the duplicates + orphaned tabs, relaunches.
cd /d "%~dp0"
python clean_and_launch_keep_one.py
echo.
echo Press any key to close...
pause >nul
