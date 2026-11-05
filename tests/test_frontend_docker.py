"""Funções da tela Docker (index.html) que transformam o que o docker devolve em números e links.
Roda o JavaScript da própria página no Node (pula se não houver Node)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HTML = (Path(__file__).resolve().parent.parent / "files/painel/index.html").read_text()
FUNCOES = ["pctNum", "memMiB", "tamMB", "pct", "portasPares"]


def _fonte(nome):
    # a declaração inteira: da linha "const nome = " até a próxima linha que começa sem espaço
    m = re.search(rf"^const {nome} = .*?(?=^\S)", HTML, re.M | re.S)
    assert m, nome
    return m.group(0)


def rodar_js(expressao):
    if not shutil.which("node"):
        pytest.skip("Node não instalado")
    repo = re.search(r"^function repoTag\(nome\)\{.*?\}$", HTML, re.M).group(0)
    codigo = "\n".join(_fonte(f) for f in FUNCOES) + "\n" + repo + f"\nconsole.log(JSON.stringify({expressao}));"
    r = subprocess.run(["node", "-e", codigo], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_memoria_do_docker_stats_em_mb():
    assert rodar_js('["10.5MiB / 256MiB", "1.5GiB / 2GiB", "512KiB / 1GiB", "0B / 0B", "", null].map(memMiB)') == [10.5, 1536, 0.5, 0, 0, 0]


def test_tamanho_de_imagem_em_mb():
    assert rodar_js('["63.2MB", "1.46GB", "13.3kB", "800B", "?"].map(tamMB)') == pytest.approx([63.2, 1460, 0.0133, 0.0008, 0])


def test_porcentagens():
    assert rodar_js('["1.25%", "0,5%", "", "abc"].map(pctNum)') == [1.25, 0.5, 0, 0]
    assert rodar_js('[0, 1.44, 9.96, 12.4, 150].map(pct)') == ["0,0%", "1,4%", "10,0%", "12%", "150%"]


def test_portas_sem_repetir_ipv4_e_ipv6():
    assert rodar_js('portasPares("0.0.0.0:8081->80/tcp, [::]:8081->80/tcp, 0.0.0.0:8443->443/tcp")') == [["8081", "80"], ["8443", "443"]]
    assert rodar_js('portasPares("80/tcp")') == []
    assert rodar_js("portasPares(null)") == []


def test_nome_e_tag_da_imagem():
    assert rodar_js('["nginx:alpine", "ubuntu", "localhost:5000/app", "localhost:5000/app:1.0", "ghcr.io/o/x:v2"].map(repoTag)') == [
        ["nginx", "alpine"], ["ubuntu", "latest"], ["localhost:5000/app", "latest"], ["localhost:5000/app", "1.0"], ["ghcr.io/o/x", "v2"]]
