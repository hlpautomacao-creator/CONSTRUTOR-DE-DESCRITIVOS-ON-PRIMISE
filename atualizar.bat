@echo off
chcp 65001 >nul 2>&1
title Construtor de Descritivo
cls
echo.
echo  ================================================
echo   Construtor de Descritivo Funcional
echo  ================================================
echo.

cd /d C:\construtor_descritivo

for /f %%i in ('git status --porcelain') do set TEM_ALTERACAO=1

if not defined TEM_ALTERACAO (
    echo  Sem alteracoes locais. Verificando GitHub...
    git pull
    goto reiniciar
)

echo  Arquivos alterados:
git status --short
echo.

for /f %%v in ('python -c "import json; d=json.load(open('changelog.json','r',encoding='utf-8')); print(d[0]['versao'] if d else 'v1.0.0')" 2^>nul') do set ULTIMA_VERSAO=%%v
if not defined ULTIMA_VERSAO set ULTIMA_VERSAO=v1.0.0
for /f %%v in ('python -c "v='%ULTIMA_VERSAO%'.lstrip('v').split('.'); v[2]=str(int(v[2])+1); print('v'+'.'.join(v))" 2^>nul') do set PROX_VERSAO=%%v
if not defined PROX_VERSAO set PROX_VERSAO=v1.0.1

echo  Ultima versao: %ULTIMA_VERSAO%
echo  Proxima versao sugerida: %PROX_VERSAO%
echo.
set /p VERSAO=  Versao [ENTER para usar sugerida]:
if "%VERSAO%"=="" set VERSAO=%PROX_VERSAO%

echo.
echo  1-Novo recurso  2-Melhoria  3-Correcao de bug  4-Manutencao
set /p CAT_NUM=  Categoria [1-4, ENTER=2]:
if "%CAT_NUM%"=="1" set CATEGORIA=Novo recurso
if "%CAT_NUM%"=="2" set CATEGORIA=Melhoria
if "%CAT_NUM%"=="3" set CATEGORIA=Correcao de bug
if "%CAT_NUM%"=="4" set CATEGORIA=Manutencao
if not defined CATEGORIA set CATEGORIA=Melhoria

echo.
set /p DESCRICAO=  Descricao do que foi alterado:
if "%DESCRICAO%"=="" set DESCRICAO=Atualizacao

echo.
set /p RESPONSAVEL=  Seu nome [ENTER para omitir]:

set COMMIT_MSG=[%VERSAO%] [%CATEGORIA%] %DESCRICAO%
if not "%RESPONSAVEL%"=="" set COMMIT_MSG=%COMMIT_MSG% - por: %RESPONSAVEL%

echo.
echo  Versao:    %VERSAO%
echo  Categoria: %CATEGORIA%
echo  Descricao: %DESCRICAO%
echo.
set /p CONFIRMA=  Confirmar e enviar? [S/N]:
if /i "%CONFIRMA%"=="N" goto cancelado
if /i "%CONFIRMA%"=="" goto cancelado

python update_changelog.py "%VERSAO%" "%CATEGORIA%" "%DESCRICAO%" "%RESPONSAVEL%"

echo.
echo  Enviando para o GitHub...
git add .
git commit -m "%COMMIT_MSG%"
git push
if not %errorlevel%==0 goto erro_push
echo  [OK] GitHub atualizado!

:reiniciar
echo.
echo  Reiniciando servidor...
docker compose up --build -d
if not %errorlevel%==0 goto erro_docker

echo.
echo  ================================================
echo   [OK] Concluido! Versao: %VERSAO%
echo   Acesse: http://localhost:5555
echo  ================================================
echo.
timeout /t 3 /nobreak >nul
start http://localhost:5555
exit

:cancelado
echo  Operacao cancelada.
pause
exit /b 0

:erro_push
echo  [ERRO] Falha ao enviar para o GitHub.
pause
exit /b 1

:erro_docker
echo  [ERRO] Falha ao reiniciar o Docker.
pause
exit /b 1
