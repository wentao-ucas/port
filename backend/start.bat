@echo off
echo 正在启动工时报工系统...
cd /d %~dp0
call conda activate tornado
python app.py
pause
