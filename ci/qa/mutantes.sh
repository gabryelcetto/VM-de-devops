#!/usr/bin/env bash
# Teste de mutantes do Painel: o mutmut cria milhares de versões do painel.py com um defeito
# pequeno cada (troca < por <=, apaga uma linha, muda um texto...) e roda os testes contra cada uma.
# Mutante "morto" = os testes perceberam o defeito. Mutante "sobrevivente" = um defeito que passaria.
# Uso: bash ci/qa/mutantes.sh [pasta-de-resultado]   (precisa de: pip install mutmut pytest)
set -uo pipefail
OUT="${1:-resultado-mutantes}"
mkdir -p "$OUT"
P=files.painel.painel
# Funções que validam o que o aluno digita, montam os comandos e protegem a pasta pessoal.
# (as que só esperam processos/threads ficam de fora: cada mutante delas só daria "tempo esgotado")
ALVOS=(x_dentro_da_home x_arquivo_permitido x_acao_arquivo x_acao_abrir x__url_git x_caminho_job
       "xǁHandlerǁhost_ok" "xǁHandlerǁdo_POST" x_ver_tarefa x_dicas_para x_ok_ou_erro x_json_linhas
       x__gatilhos x__texto_erro x_criar_credencial x_xml_item x_acao_docker x_acao_git x_acao_executar x_acao_jenkins)
rm -rf mutants
timeout 5400 mutmut run --max-children "$(nproc)" "${ALVOS[@]/#/$P.}"  # mutmut aceita padrões com *
mutmut results --all true > "$OUT/mutantes-todos.txt" 2>/dev/null || mutmut results > "$OUT/mutantes-todos.txt"
python3 - "$OUT" <<'PY'
import collections, re, sys
out = sys.argv[1]
linhas = open(f"{out}/mutantes-todos.txt").read().splitlines()
por = collections.defaultdict(collections.Counter)
for l in linhas:
    m = re.match(r"\s*files\.painel\.painel\.(x\S*?)__mutmut_\d+: (.+)$", l)
    if m:
        por[m.group(1)][m.group(2).strip()] += 1
tot = collections.Counter()
rel = ["Teste de mutantes do painel.py", "", f"{'função':40} {'mortos':>7} {'sobrev.':>7} {'tempo':>6} {'nota':>6}"]
for f, c in sorted(por.items()):
    mortos = c["killed"] + c["timeout"]
    vivos = c["survived"]
    tot.update(c)
    if mortos + vivos:
        rel.append(f"{f.replace('ǁ', '.'):40} {c['killed']:7} {vivos:7} {c['timeout']:6} {100 * mortos / (mortos + vivos):5.0f}%")
mortos, vivos = tot["killed"] + tot["timeout"], tot["survived"]
nota = 100 * mortos / max(1, mortos + vivos)
rel += ["", f"TOTAL: {mortos} mortos, {vivos} sobreviventes, {tot['not checked']} não rodados -> nota {nota:.1f}%"]
open(f"{out}/MUTANTES.txt", "w").write("\n".join(rel) + "\n")
print("\n".join(rel))
PY
