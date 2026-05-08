@echo off
chcp 65001 >nul
title GetNotes

cd /d "%~dp0"

echo.
echo ========================================
echo   GetNotes - URL 转笔记工具
echo ========================================
echo.

:: 检查 Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.9+
    pause
    exit /b 1
)

:: 创建虚拟环境 (如果不存在)
if not exist "venv\Scripts\activate.bat" (
    echo [创建虚拟环境...]
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
)

:: 激活虚拟环境
call venv\Scripts\activate.bat

:: 安装依赖
echo [检查依赖...]
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo [错误] 安装依赖失败
    pause
    exit /b 1
)

:: 检查 .env 文件
if not exist ".env" (
    echo [警告] 未找到 .env 文件，请复制 .env.example 并填入 API Key
    copy .env.example .env >nul 2>&1
)

echo.
echo [启动] http://127.0.0.1:5000
echo ========================================
echo.

python app.py

pause
