@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo    LumiBox - Windows 综合工具箱 · 一键打包为 exe
echo    请使用 python.org 官方安装包（需 3.10+，且带完整标准库）
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 Python，请安装 Python 3.10 或更高版本并勾选 "Add Python to PATH"
    pause
    exit /b 1
)

echo [1/3] 安装 / 校验依赖...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

echo [2/3] 清理旧的构建产物...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/3] 使用 PyInstaller 打包（单文件 + 无控制台窗口）...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name "LumiBox" ^
    --icon "assets\app_icon.ico" ^
    --add-data "assets\app_icon.ico;assets" ^
    --collect-submodules qrcode ^
    --collect-submodules pptx ^
    --collect-submodules markdown ^
    --collect-submodules yaml ^
    --collect-all pymupdf ^
    --collect-all zxingcpp ^
    --collect-all reportlab ^
    --collect-all weasyprint ^
    --collect-all cryptography ^
    --collect-all openpyxl ^
    --hidden-import qrcode.image.pil ^
    --hidden-import qrcode.image.base ^
    --hidden-import PIL.Image ^
    --hidden-import psutil ^
    --hidden-import pymupdf ^
    --hidden-import fitz ^
    --hidden-import reportlab.pdfgen ^
    --hidden-import pptx.util ^
    --hidden-import tomli_w ^
    --hidden-import tomllib ^
    --hidden-import pytesseract ^
    --hidden-import cryptography.fernet ^
    --hidden-import cryptography.hazmat.primitives.kdf.pbkdf2 ^
    --hidden-import openpyxl.cell._writer ^
    main.py
if errorlevel 1 (
    echo [错误] 打包失败，请查看上方日志
    pause
    exit /b 1
)

echo.
echo ============================================================
echo    打包完成！可执行文件：dist\LumiBox.exe
echo    单文件绿色程序，可直接复制到其他 Windows 电脑运行
echo ============================================================
pause
