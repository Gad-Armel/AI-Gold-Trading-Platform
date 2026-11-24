@echo off
setlocal
cd /d "%~dp0"
python -B "tools\launch_gold_demo.py" --background --yes-demo-risk
if errorlevel 1 (
    echo.
    pause
)
