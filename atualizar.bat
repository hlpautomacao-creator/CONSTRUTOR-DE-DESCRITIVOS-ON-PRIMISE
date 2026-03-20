@echo off
title Construtor de Descritivo - Atualizacao
cls

echo.
echo  ====================================================
echo   Construtor de Descritivo Funcional
echo   Aplicando atualizacoes...
echo  ====================================================
echo.

cd /d C:\construtor_descritivo

:: Verificar se ha alteracoes locais para enviar
for /f %%i in ('git status --porcelain') do set TEM_ALTERACAO=1

if not defined TEM_ALTERACAO (
    echo  Nenhuma alteracao local encontrada.
    echo  Verificando atualizacoes no servidor...
    git pull
    goto reiniciar
)

:: Mostrar arquivos alterados
echo  Arquivos alterados:
git status --short
echo.

:: Pedir descricao
set /p DESCRICAO=  Descreva o que foi alterado: 
if "%DESCRICAO%"=="" set DESCRICAO=atualizacao

:: Enviar para o GitHub
echo.
echo  Enviando para o GitHub...
git add .
git commit -m "%DESCRICAO%"
git push

if %errorlevel% neq 0 (
    echo.
    echo  [ERRO] Falha ao enviar para o GitHub.
    pause
    exit /b 1
)

echo.
echo  [OK] Enviado ao GitHub com sucesso!

:reiniciar
echo.
echo  Reiniciando o servidor...
docker compose up --build -d

if %errorlevel% neq 0 (
    echo.
    echo  [ERRO] Falha ao reiniciar. Verifique o Docker Desktop.
    pause
    exit /b 1
)

echo.
echo  ====================================================
echo   [OK] Atualizacao concluida!
echo   Acesse: http://localhost:5555
echo  ====================================================
echo.
timeout /t 3 /nobreak >nul
start http://localhost:5555
exit
