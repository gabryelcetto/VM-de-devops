#!/usr/bin/env python3
"""Checagem estrutural da tela do Painel (files/painel/index.html) contra o servidor (painel.py).

1. O JavaScript da página não tem erro de sintaxe (node --check).
2. Todo endereço /api/... chamado pela tela existe no servidor (GET ou POST).
3. Toda função chamada em botões e menus (onclick, BT(...), M([...js:...])) existe na página.
4. Toda "ferramenta"/"acao" que a tela manda para /api/executar existe no servidor.
Uso: python3 ci/qa/checar-frontend.py   (sai com erro se achar problema)
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
HTML = (RAIZ / "files/painel/index.html").read_text()
PY = (RAIZ / "files/painel/painel.py").read_text()
problemas = []

js = "\n".join(re.findall(r"<script>([\s\S]*?)</script>", HTML))
with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
    f.write(js)
r = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
if r.returncode != 0:
    problemas.append("JavaScript com erro de sintaxe:\n" + r.stderr[-1500:])

# 2. endpoints
rotas = PY[PY.index("GETS = {"):PY.index("class Handler")]
no_servidor = set(re.findall(r'"(/api/[a-z\-]+)"', rotas))
na_tela = set(re.findall(r"['\"`](/api/[a-z\-]+)", js))
for ep in sorted(na_tela - no_servidor):
    problemas.append(f"a tela chama {ep}, que não existe no servidor")

# 3. funções chamadas pelos botões
definidas = set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)", js))
definidas |= set(re.findall(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=", js))
globais = {"if", "confirm", "prompt", "alert", "encodeURIComponent", "JSON", "Number", "String", "setTimeout",
           "fetch", "navigator", "window", "document", "Math", "Date", "Object", "Array", "Set", "event", "this"}
handlers = re.findall(r'on\w+="([^"]*)"', HTML)
handlers += [m.group(2) for m in re.finditer(r"\bBT\((`[^`]*`|'[^']*'|\"[^\"]*\")\s*,\s*(`[^`]*`|'[^']*'|\"[^\"]*\")", js)]
handlers += re.findall(r"\bjs:\s*(`[^`]*`|'[^']*'|\"[^\"]*\")", js)
for h in handlers:
    h = re.sub(r"\$\{[^}]*\}", "X", h)  # trechos ${...} viram um valor qualquer
    h = re.sub(r"'[^']*'|\"[^\"]*\"", "''", h.strip("`'\""))  # textos dentro do código
    for nome in re.findall(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(", h):
        if nome not in definidas and nome not in globais:
            problemas.append(f"um botão chama {nome}(), que não existe na página: {h[:120]}")

# 4. ferramentas/ações de /api/executar
exe = PY[PY.index("def acao_executar"):PY.index("def _pastas_projetos")]
for ferr, acao in sorted(set(re.findall(r"ferramenta:\s*['\"](\w+)['\"]\s*,\s*acao:\s*['\"](\w+)['\"]", js))):
    if f'f == "{ferr}"' not in exe:
        problemas.append(f"a tela usa a ferramenta '{ferr}' em /api/executar, que o servidor não conhece")
    elif f'"{acao}"' not in exe:
        problemas.append(f"a tela usa a ação '{acao}' da ferramenta '{ferr}', que o servidor não conhece")

print(f"funções na página: {len(definidas)} | endpoints na tela: {len(na_tela)} | botões checados: {len(handlers)}")
if problemas:
    print("\n".join("PROBLEMA: " + x for x in dict.fromkeys(problemas)))
    sys.exit(1)
print("Tela e servidor estão coerentes.")
