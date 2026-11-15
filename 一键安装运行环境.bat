@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo    LumiBox - Windows 综合工具箱 · 一键安装运行环境
echo    本脚本将: 检查 Python - 安装依赖 - 校验环境 - 启动程序
echo ============================================================
echo.

rem ---------- 第 1 步: 定位可用的 Python ----------
set "PY="
where python >nul 2>nul
if not errorlevel 1 set "PY=python"
if not defined PY (
    where py >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
    echo [错误] 未找到 Python。
    echo        请到 https://www.python.org/downloads/ 下载 Python 3.10 或更高版本,
    echo        安装时务必勾选 "Add Python to PATH", 然后重新运行本脚本。
    start https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [1/5] 使用 Python: %PY%

rem ---------- 第 2 步: 检查版本(需 3.10+) ----------
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo [错误] Python 版本过低, LumiBox 需要 Python 3.10 及以上。
    %PY% --version
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('%PY% --version') do echo [2/5] 版本检查通过: %%v

rem ---------- 第 3 步: 升级 pip ----------
echo [3/5] 升级 pip...
%PY% -m pip install --upgrade pip -q
if errorlevel 1 echo        (pip 升级跳过或失败, 继续安装依赖)

rem ---------- 第 4 步: 安装依赖(默认源失败自动切清华镜像) ----------
echo [4/5] 安装依赖, 首次约需 3~10 分钟, 请耐心等待...
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo        默认源安装失败, 自动切换清华镜像源重试...
    %PY% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo [错误] 依赖安装失败, 请检查网络后重新运行本脚本。
        pause
        exit /b 1
    )
)

rem ---------- 第 5 步: 依赖自检 ----------
echo [5/5] 校验核心依赖是否安装完整...
%PY% -c "import PySide6, psutil, qrcode, PIL, zxingcpp, pptx, fitz, reportlab, yaml, tomli_w, markdown, openpyxl, cryptography; print('       核心依赖全部就绪')"
if errorlevel 1 (
    echo [错误] 部分核心依赖缺失, 请把上方报错信息截图反馈。
    pause
    exit /b 1
)

rem ---------- 可选组件提示 ----------
echo.
echo ------------------------------------------------------------
echo  可选组件检测 (缺失不报错, 仅影响对应功能):
where tesseract >nul 2>nul
if errorlevel 1 (
    echo    [!] 未检测到 tesseract-ocr, OCR 文字识别不可用
    echo        安装: https://github.com/UB-Mannheim/tesseract/wiki
) else (
    echo    [OK] tesseract-ocr 已安装, OCR 可用
)
where soffice >nul 2>nul
if errorlevel 1 (
    echo    [!] 未检测到 LibreOffice, PPT 旧格式互转不可用
    echo        安装: https://www.libreoffice.org/download
) else (
    echo    [OK] LibreOffice 已安装, 文档转换功能完整
)
echo ------------------------------------------------------------
echo.
echo ============================================================
echo    环境安装完成! 正在启动 LumiBox...
echo    以后想直接运行: 双击 run.bat, 或执行 python main.py
echo ============================================================
echo.

%PY% main.py
if errorlevel 1 (
    echo.
    echo [提示] 程序异常退出, 请把上方报错信息截图反馈。
)
echo.
echo 窗口可以关闭了。按任意键退出...
pause >nul
endlocal
