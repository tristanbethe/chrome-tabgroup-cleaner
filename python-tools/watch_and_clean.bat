@echo off
REM Watch & Clean - keeps running in the background and cleans up every time
REM Chrome closes. Put a shortcut to this file in your Startup folder to
REM run it automatically at login (shell:startup).
cd /d "%~dp0"
python watch_and_clean.py
pause
