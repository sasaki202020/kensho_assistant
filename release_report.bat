@echo off
cd /d %~dp0
set PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe
if exist "%PYTHON_EXE%" (
  "%PYTHON_EXE%" main.py release-report
) else (
  py -3 main.py release-report
  if errorlevel 9009 python main.py release-report
)
pause
