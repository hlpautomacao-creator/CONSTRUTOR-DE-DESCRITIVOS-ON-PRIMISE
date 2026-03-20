@echo off
title Construtor de Descritivo Funcional
cls

echo.
echo  ====================================================
echo   Construtor de Descritivo Funcional
echo   Toledo do Brasil
echo  ====================================================
echo.

:: Verificar se Docker esta rodando
docker info >nul 2>&1
if %errorlevel% neq 0 (
    echo  [!] Docker nao esta rodando.
    echo.
    echo  Abrindo Docker Desktop... aguarde ficar verde
    echo  e execute este arquivo novamente.
    echo.
    start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    pause
    exit /b 1
)

echo  Iniciando servidor...
echo.

cd /d "%~dp0"
docker compose up -d

if %errorlevel% neq 0 (
    echo.
    echo  [ERRO] Falha ao iniciar. Verifique o Docker Desktop.
    pause
    exit /b 1
)

echo.
echo  Aguardando servidor ficar pronto...
timeout /t 5 /nobreak >nul

echo.
echo  ====================================================
echo   Acesse no navegador:
echo   http://localhost:5555
echo  ====================================================
echo.

start http://localhost:5555
exit
