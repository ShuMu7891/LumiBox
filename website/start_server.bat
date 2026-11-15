@echo off
title LumiBox 官网 + 留言板服务
cd /d "%~dp0"

echo.
echo   ============================================
echo    LumiBox 官网与留言板服务
echo   ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo   [错误] 未找到 Python，请先安装 Python 3.8 或更高版本
  echo          下载地址: https://www.python.org/downloads/
  echo          安装时请勾选 Add Python to PATH
  echo.
  pause
  exit /b 1
)

if not defined LUMIBOX_ADMIN_TOKEN (
  echo   [提示] 未设置 LUMIBOX_ADMIN_TOKEN，将使用默认管理口令
  echo          正式上线前请务必改成自己的口令，例如:
  echo          set LUMIBOX_ADMIN_TOKEN=你的复杂口令
  echo.
)

echo   正在启动，浏览器打开: http://127.0.0.1:8080/
echo   按 Ctrl+C 可停止服务
echo.

python server.py
pause
