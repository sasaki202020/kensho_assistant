@echo off
cd /d %~dp0
if "%~1"=="" (
  echo campaign_id を指定してください。
  echo 例: start_chrome_prepare.bat rayhv4hzz668yhac
  pause
  exit /b 1
)
set PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe
if exist "%PYTHON_EXE%" (
  "%PYTHON_EXE%" main.py prepare --campaign-id %1 --browser chrome --keep-open --no-screenshot --require-user-approved
) else (
  py -3 main.py prepare --campaign-id %1 --browser chrome --keep-open --no-screenshot --require-user-approved
  if errorlevel 9009 python main.py prepare --campaign-id %1 --browser chrome --keep-open --no-screenshot --require-user-approved
)
if errorlevel 1 (
  echo.
  echo Chrome応募準備中にエラーが発生しました。
  pause
)
