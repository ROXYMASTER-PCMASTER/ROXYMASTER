@echo off
chcp 65001 >nul
title ROXYMASTER PCMASTER v8.0

echo.
echo ============================================================
echo   🏰  ROXYMASTER v8.0 — PCMASTER SERVER
echo ============================================================
echo.

cd /d "%~dp0.."
set "PYTHONPATH=%~dp0.."

echo [*] Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Python no encontrado. Instala Python 3.10+
    pause
    exit /b 1
)

echo [*] Verificando dependencias...
python -c "import websockets, requests, psutil, json" >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Instalando dependencias...
    pip install websockets requests psutil --quiet
)

echo.
echo [*] Iniciando PCMASTER Server...
echo.

python -m pcmaster.scripts.main

pause