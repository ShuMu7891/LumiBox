@echo off
setlocal
cd /d "%~dp0"

set "PY="
where python >nul 2>nul
if not errorlevel 1 set "PY=python"
if not defined PY (
    where py >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
    echo [错误] 未找到 Python, 请先运行「一键安装运行环境.bat」
    pause
    exit /b 1
)

%PY% main.py
if errorlevel 1 (
    echo.
    echo [提示] 程序异常退出。若提示缺少模块, 请先运行「一键安装运行环境.bat」
)
echo.
echo 程序已退出, 按任意键关闭窗口...
pause >nul
endlocal
