@echo off
echo ========================================
echo    构建前端生产版本
echo ========================================
echo.

cd frontend
npm run build

echo.
echo 构建完成！静态文件位于 frontend/dist/
pause
