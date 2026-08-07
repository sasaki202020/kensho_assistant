@echo off
setlocal
cd /d "%~dp0"

py -3 main.py collect --limit 30
if errorlevel 1 exit /b %errorlevel%

py -3 main.py build-queue --limit 30
if errorlevel 1 exit /b %errorlevel%

py -3 main.py research-report
exit /b %errorlevel%
