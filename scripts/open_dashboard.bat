@echo off
cd /d %~dp0..
if exist "reports\index.html" (
  start "" "reports\index.html"
) else (
  echo reports\index.html not found.
)
