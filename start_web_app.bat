@echo off
cd /d %~dp0
set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if exist "%PYTHON_EXE%" (
  "%PYTHON_EXE%" web_app.py
) else (
  py -3 web_app.py
  if errorlevel 9009 python web_app.py
)
if errorlevel 1 (
  echo.
  echo Webアプリ起動中にエラーが発生しました。
  pause
)
