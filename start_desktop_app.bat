@echo off
cd /d %~dp0
set PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe
if exist "%PYTHON_EXE%" (
  "%PYTHON_EXE%" desktop_app.py
) else (
  py -3 desktop_app.py
  if errorlevel 9009 python desktop_app.py
)
if errorlevel 1 (
  echo.
  echo 起動中にエラーが発生しました。
  pause
)
