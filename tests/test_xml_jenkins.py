"""XML de cada tipo de item do Jenkins comparado com o XML aprovado (tests/xml_esperado/).
Esses XMLs foram aceitos e construídos pelo Jenkins de verdade no laboratório; qualquer mudança
no que o painel gera aparece aqui. Para aprovar uma mudança de propósito: APROVAR_XML=1 pytest."""
import os
import re
from pathlib import Path

import pytest

PASTA = Path(__file__).parent / "xml_esperado"
CASOS = {
    "pipeline": {"script": "pipeline { agent any }", "cron": "H 8 * * 1-5", "descricao": "Meu pipeline"},
    "pipeline-padrao": {},
    "pipeline_scm": {"repo": "https://github.com/gabryel/app.git", "branch": "dev", "jenkinsfile": "ci/Jenkinsfile",
                     "credencial": "github", "cron_scm": "H/5 * * * *"},
    "freestyle": {"comandos": "echo ok", "cron": "@daily", "cron_scm": "H/15 * * * *"},
    "freestyle-git": {"repo": "git@github.com:gabryel/app.git", "credencial": "ssh"},
    "multibranch": {"repo": "https://github.com/gabryel/app.git", "credencial": "github", "jenkinsfile": "Jenkinsfile.ci"},
    "pasta": {"descricao": "Projetos da aula"},
}


@pytest.mark.parametrize("nome", sorted(CASOS))
def test_xml_igual_ao_aprovado(p, nome):
    tipo = nome.split("-")[0]
    xml = p.xml_item(tipo, CASOS[nome]).decode()
    xml = re.sub(r"<id>[0-9a-f]{16}</id>", "<id>ALEATORIO</id>", xml)  # id do multibranch muda a cada vez
    arq = PASTA / f"{nome}.xml"
    if os.environ.get("APROVAR_XML") or not arq.exists():
        arq.write_text(xml)
    assert xml == arq.read_text()
