@echo off
cd /d %~dp0..
set PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python
"%PYTHON_EXE%" -m src.marketplace_writer --open-latest --report-root reports
echo.
echo Marketplace helper opened.
pause
