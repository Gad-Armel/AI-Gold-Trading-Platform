@echo off
setlocal
cd /d "%~dp0"
python -B "tools\launch_gold_demo.py"
if errorlevel 1 (
    echo.
    pause
)
