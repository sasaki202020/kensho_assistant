@echo off
cd /d %~dp0
set PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe
if exist "%PYTHON_EXE%" (
  "%PYTHON_EXE%" main.py doctor
  "%PYTHON_EXE%" main.py profile check
) else (
  py -3 main.py doctor
  py -3 main.py profile check
  if errorlevel 9009 (
    python main.py doctor
    python main.py profile check
  )
)
pause
