@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
if "%PYTHON_EXE%"=="" set "PYTHON_EXE=py -3.13"
cd /d "%PROJECT_ROOT%"
%PYTHON_EXE% daily_run.py --phase morning %*
exit /b %ERRORLEVEL%
