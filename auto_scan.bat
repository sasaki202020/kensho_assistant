@echo off
cd /d %~dp0
set PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe
if exist "%PYTHON_EXE%" (
  "%PYTHON_EXE%" main.py collect --limit 30
  "%PYTHON_EXE%" main.py analyze
  "%PYTHON_EXE%" main.py resolve-urls --limit 30
  "%PYTHON_EXE%" main.py inspect-form --limit 20
  "%PYTHON_EXE%" main.py review --limit 10
  "%PYTHON_EXE%" main.py build-queue --limit 30
  "%PYTHON_EXE%" main.py research-report
  "%PYTHON_EXE%" main.py release-report
) else (
  py -3 main.py collect --limit 30
  py -3 main.py analyze
  py -3 main.py resolve-urls --limit 30
  py -3 main.py inspect-form --limit 20
  py -3 main.py review --limit 10
  py -3 main.py build-queue --limit 30
  py -3 main.py research-report
  py -3 main.py release-report
  if errorlevel 9009 (
    python main.py collect --limit 30
    python main.py analyze
    python main.py resolve-urls --limit 30
    python main.py inspect-form --limit 20
    python main.py review --limit 10
    python main.py build-queue --limit 30
    python main.py research-report
    python main.py release-report
  )
)
echo.
echo Auto scan complete.
echo No submission was performed.
pause
