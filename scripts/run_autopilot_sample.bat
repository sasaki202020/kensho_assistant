@echo off
cd /d %~dp0..
set PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe
if exist "%PYTHON_EXE%" (
  "%PYTHON_EXE%" -m src.autopilot --sample --limit 5
) else (
  python -m src.autopilot --sample --limit 5
)
echo.
echo Autopilot sample complete.
pause
