@echo off
echo ========================================
echo    工时报工系统 - 快速启动脚本
echo ========================================
echo.

echo 正在激活 tornado 环境...
call conda activate tornado

echo 正在启动后端服务...
cd backend
start "工时报工后端" python app.py

echo.
echo ========================================
echo 服务已启动！
echo 访问地址: http://localhost:18760
echo 按 Ctrl+C 可以停止服务
echo ========================================
pause
