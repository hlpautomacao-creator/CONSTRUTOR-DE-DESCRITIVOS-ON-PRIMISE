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

:: ── Preencher informacoes do changelog ─────────────────────────
echo  Preencha as informacoes para o changelog:
echo  (Pressione ENTER para usar o valor padrao entre colchetes)
echo.

:: Versao
set /p VERSAO=  Versao [ex: v1.0.1]: 
if "%VERSAO%"=="" set VERSAO=v1.0.0

:: Categoria
echo.
echo  Categorias disponiveis:
echo    1 - Novo recurso
echo    2 - Melhoria
echo    3 - Correcao de bug
echo    4 - Manutencao
echo.
set /p CAT_NUM=  Escolha a categoria [1-4]: 

if "%CAT_NUM%"=="1" set CATEGORIA=Novo recurso
if "%CAT_NUM%"=="2" set CATEGORIA=Melhoria
if "%CAT_NUM%"=="3" set CATEGORIA=Correcao de bug
if "%CAT_NUM%"=="4" set CATEGORIA=Manutencao
if not defined CATEGORIA set CATEGORIA=Melhoria

:: Descricao
echo.
set /p DESCRICAO=  Descreva o que foi alterado: 
if "%DESCRICAO%"=="" set DESCRICAO=Atualizacao sem descricao

:: Responsavel
echo.
set /p RESPONSAVEL=  Seu nome [deixe vazio para usar o do Git]: 

:: Montar mensagem de commit formatada
set COMMIT_MSG=[%VERSAO%] [%CATEGORIA%] %DESCRICAO%
if not "%RESPONSAVEL%"=="" set COMMIT_MSG=%COMMIT_MSG% ^| por: %RESPONSAVEL%

echo.
echo  ── Resumo ──────────────────────────────────────────
echo   Versao:     %VERSAO%
echo   Categoria:  %CATEGORIA%
echo   Descricao:  %DESCRICAO%
if not "%RESPONSAVEL%"=="" echo   Responsavel: %RESPONSAVEL%
echo  ────────────────────────────────────────────────────
echo.

set /p CONFIRMA=  Confirmar e enviar? [S/N]: 
if /i not "%CONFIRMA%"=="S" (
    echo  Cancelado.
    pause
    exit /b 0
)

:: Enviar para o GitHub
echo.
echo  Enviando para o GitHub...
git add .
git commit -m "%COMMIT_MSG%"
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
