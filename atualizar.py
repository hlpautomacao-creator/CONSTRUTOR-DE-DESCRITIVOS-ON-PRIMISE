# -*- coding: utf-8 -*-
import subprocess, sys, json, datetime, os

os.chdir(r"C:\construtor_descritivo")

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()

def ask(prompt, default=""):
    try:
        val = input(prompt).strip()
        return val if val else default
    except:
        return default

def git(cmd):
    return os.system("git " + cmd)

print()
print("  ================================================")
print("   Construtor de Descritivo Funcional")
print("   Aplicando atualizacoes...")
print("  ================================================")
print()

status = run("git status --porcelain")
if not status:
    print("  Sem alteracoes locais. Verificando GitHub...")
    git("pull")
    print()
    print("  Reiniciando servidor...")
    os.system("docker compose up --build -d")
    print()
    print("  [OK] Servidor atualizado!")
    input("  Pressione ENTER para sair...")
    sys.exit(0)

print("  Arquivos alterados:")
git("status --short")
print()

try:
    with open("changelog.json", "r", encoding="utf-8") as f:
        changelog = json.load(f)
    ultima = changelog[0]["versao"] if changelog else "v1.0.0"
except:
    ultima = "v1.0.0"

try:
    partes = ultima.lstrip("v").split(".")
    prox = "v{}.{}.{}".format(partes[0], partes[1], int(partes[2]) + 1)
except:
    prox = "v1.0.1"

print("  Ultima versao : " + ultima)
print("  Proxima versao: " + prox)
print()

versao = ask("  Versao [ENTER = " + prox + "]: ", prox)

print()
print("  Selecione a categoria:")
print("    1  Novo recurso")
print("    2  Melhoria")
print("    3  Correcao de bug")
print("    4  Manutencao")
print()

cat_map = {"1": "Novo recurso", "2": "Melhoria", "3": "Correcao de bug", "4": "Manutencao"}
cat_num = ask("  Categoria [1-4, ENTER=2]: ", "2")
categoria = cat_map.get(cat_num, "Melhoria")

print()
descricao = ask("  Descricao do que foi alterado: ", "Atualizacao")

print()
responsavel = ask("  Seu nome [ENTER para omitir]: ", "")

print()
print("  ------------------------------------------------")
print("   Versao    : " + versao)
print("   Categoria : " + categoria)
print("   Descricao : " + descricao)
if responsavel:
    print("   Por       : " + responsavel)
print("  ------------------------------------------------")
print()

confirma = ask("  Confirmar e enviar? [S/N]: ", "N")
if confirma.upper() != "S":
    print("  Cancelado.")
    input("  Pressione ENTER para sair...")
    sys.exit(0)

try:
    with open("changelog.json", "r", encoding="utf-8") as f:
        data = json.load(f)
except:
    data = []

data.insert(0, {
    "versao": versao,
    "data": datetime.date.today().isoformat(),
    "categoria": categoria,
    "descricao": descricao,
    "responsavel": responsavel
})

with open("changelog.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print()
print("  [OK] changelog.json atualizado")

# Montar mensagem do commit sem aspas duplas embutidas
partes_msg = [versao, categoria, descricao]
if responsavel:
    partes_msg.append("por: " + responsavel)
commit_msg = "[{}] [{}] {}".format(versao, categoria, descricao)
if responsavel:
    commit_msg += " - por: " + responsavel

# Usar subprocess para evitar problemas com aspas no os.system
print()
print("  Enviando para o GitHub...")
git("add .")
subprocess.run(["git", "commit", "-m", commit_msg])
ret = subprocess.run(["git", "push"]).returncode

if ret != 0:
    print()
    print("  [ERRO] Falha ao enviar para o GitHub.")
    input("  Pressione ENTER para sair...")
    sys.exit(1)

print("  [OK] GitHub atualizado!")

print()
print("  Reiniciando servidor...")
ret = os.system("docker compose up --build -d")
if ret != 0:
    print()
    print("  [ERRO] Falha ao reiniciar o Docker.")
    input("  Pressione ENTER para sair...")
    sys.exit(1)

print()
print("  ================================================")
print("   [OK] Concluido! Versao: " + versao)
print("   Acesse: http://localhost:5555")
print("  ================================================")
print()
os.system("start http://localhost:5555")
input("  Pressione ENTER para fechar...")
