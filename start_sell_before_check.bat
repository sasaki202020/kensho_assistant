@echo off
cd /d %~dp0
echo 売る前チェックを起動します: http://127.0.0.1:8788
start "" http://127.0.0.1:8788
py -3 run_sell_before_check.py
pause
