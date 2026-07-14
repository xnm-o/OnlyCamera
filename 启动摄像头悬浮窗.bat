@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
python -X utf8 main.py
if errorlevel 1 (
    echo.
    echo 启动失败，请检查摄像头是否已连接。
    pause
)
