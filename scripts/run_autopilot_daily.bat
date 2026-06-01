@echo off
cd /d %~dp0..
set PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python
if defined AUTOPILOT_AREA if defined AUTOPILOT_INDUSTRY (
  "%PYTHON_EXE%" -m src.autopilot --area "%AUTOPILOT_AREA%" --industry "%AUTOPILOT_INDUSTRY%" --limit 20
) else (
  "%PYTHON_EXE%" -m src.autopilot --sample --limit 20
)
echo.
echo Autopilot daily run complete.
pause
