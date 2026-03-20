# Construtor de Descritivo Funcional - Script de Atualizacao
# Execute com duplo clique ou: powershell -ExecutionPolicy Bypass -File atualizar.ps1

Set-Location "C:\construtor_descritivo"
$Host.UI.RawUI.WindowTitle = "Construtor de Descritivo - Atualizacao"
Clear-Host

Write-Host ""
Write-Host "  ================================================" -ForegroundColor Cyan
Write-Host "   Construtor de Descritivo Funcional" -ForegroundColor White
Write-Host "   Aplicando atualizacoes..." -ForegroundColor Gray
Write-Host "  ================================================" -ForegroundColor Cyan
Write-Host ""

# Verificar alteracoes locais
$status = git status --porcelain
if (-not $status) {
    Write-Host "  Sem alteracoes locais. Verificando GitHub..." -ForegroundColor Yellow
    git pull
    & "$PSScriptRoot\reiniciar.ps1" 2>$null
    goto reiniciar
}

Write-Host "  Arquivos alterados:" -ForegroundColor Yellow
git status --short
Write-Host ""

# Pegar ultima versao do changelog
try {
    $changelog = Get-Content "changelog.json" -Encoding UTF8 | ConvertFrom-Json
    $ultimaVersao = $changelog[0].versao
} catch {
    $ultimaVersao = "v1.0.0"
}

# Calcular proxima versao automaticamente
$partes = $ultimaVersao.TrimStart('v').Split('.')
$proxPatch = [int]$partes[2] + 1
$proxVersao = "v$($partes[0]).$($partes[1]).$proxPatch"

Write-Host "  Ultima versao registrada : $ultimaVersao" -ForegroundColor Gray
Write-Host "  Proxima versao sugerida  : $proxVersao" -ForegroundColor Green
Write-Host ""

$versaoInput = Read-Host "  Versao [ENTER para usar $proxVersao]"
if ([string]::IsNullOrWhiteSpace($versaoInput)) { $versao = $proxVersao } else { $versao = $versaoInput }

# Selecao de categoria
Write-Host ""
Write-Host "  Selecione a categoria:" -ForegroundColor Cyan
Write-Host "    1  Novo recurso" -ForegroundColor Green
Write-Host "    2  Melhoria" -ForegroundColor Blue
Write-Host "    3  Correcao de bug" -ForegroundColor Red
Write-Host "    4  Manutencao" -ForegroundColor Gray
Write-Host ""

$catNum = Read-Host "  Categoria [1-4, ENTER=2]"
switch ($catNum) {
    "1" { $categoria = "Novo recurso" }
    "3" { $categoria = "Correcao de bug" }
    "4" { $categoria = "Manutencao" }
    default { $categoria = "Melhoria" }
}

Write-Host ""
$descricao = Read-Host "  Descricao do que foi alterado"
if ([string]::IsNullOrWhiteSpace($descricao)) { $descricao = "Atualizacao" }

Write-Host ""
$responsavel = Read-Host "  Seu nome [ENTER para omitir]"

# Resumo
Write-Host ""
Write-Host "  ================================================" -ForegroundColor Cyan
Write-Host "   Versao    : $versao" -ForegroundColor White
Write-Host "   Categoria : $categoria" -ForegroundColor White
Write-Host "   Descricao : $descricao" -ForegroundColor White
if ($responsavel) { Write-Host "   Por       : $responsavel" -ForegroundColor White }
Write-Host "  ================================================" -ForegroundColor Cyan
Write-Host ""

$confirma = Read-Host "  Confirmar e enviar? [S/N]"
if ($confirma -notmatch "^[Ss]$") {
    Write-Host "  Operacao cancelada." -ForegroundColor Yellow
    Read-Host "  Pressione ENTER para sair"
    exit
}

# Atualizar changelog.json
python update_changelog.py "$versao" "$categoria" "$descricao" "$responsavel"

# Montar mensagem do commit
$commitMsg = "[$versao] [$categoria] $descricao"
if ($responsavel) { $commitMsg += " - por: $responsavel" }

# Enviar para o GitHub
Write-Host ""
Write-Host "  Enviando para o GitHub..." -ForegroundColor Cyan
git add .
git commit -m $commitMsg
git push

if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERRO] Falha ao enviar para o GitHub." -ForegroundColor Red
    Read-Host "  Pressione ENTER para sair"
    exit 1
}
Write-Host "  [OK] GitHub atualizado!" -ForegroundColor Green

# Reiniciar
:reiniciar
Write-Host ""
Write-Host "  Reiniciando servidor..." -ForegroundColor Cyan
docker compose up --build -d

if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERRO] Falha ao reiniciar o Docker." -ForegroundColor Red
    Read-Host "  Pressione ENTER para sair"
    exit 1
}

Write-Host ""
Write-Host "  ================================================" -ForegroundColor Green
Write-Host "   [OK] Concluido! Versao: $versao" -ForegroundColor Green
Write-Host "   Acesse: http://localhost:5555" -ForegroundColor White
Write-Host "  ================================================" -ForegroundColor Green
Write-Host ""
Start-Sleep -Seconds 2
Start-Process "http://localhost:5555"
