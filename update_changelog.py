import sys, json, datetime

versao     = sys.argv[1] if len(sys.argv) > 1 else 'v1.0.0'
categoria  = sys.argv[2] if len(sys.argv) > 2 else 'Melhoria'
descricao  = sys.argv[3] if len(sys.argv) > 3 else 'Atualizacao'
responsavel= sys.argv[4] if len(sys.argv) > 4 else ''

try:
    with open('changelog.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
except:
    data = []

entry = {
    'versao': versao,
    'data': datetime.date.today().isoformat(),
    'categoria': categoria,
    'descricao': descricao,
    'responsavel': responsavel
}
data.insert(0, entry)

with open('changelog.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('  [OK] changelog.json atualizado: ' + versao)
