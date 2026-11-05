"""Testes do Painel DevOps (files/painel/painel.py).

O painel lê a pasta pessoal (HOME) quando é importado, então a HOME de teste é criada
antes do import. Nada aqui usa Docker, Jenkins ou rede: os comandos externos são
capturados (fixture `cmds`), exceto o git, que roda de verdade em pastas temporárias.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# a mesma HOME em todas as rodadas do mesmo processo (o teste de mutantes roda o pytest várias vezes)
_HOME = Path(os.environ.setdefault("PAINEL_TESTE_HOME", tempfile.mkdtemp(prefix="painel-home-"))).resolve()
_HOME.mkdir(parents=True, exist_ok=True)
os.environ["HOME"] = str(_HOME)
os.environ["PAINEL_PORTA"] = "18090"
os.environ["GIT_CONFIG_GLOBAL"] = str(_HOME / ".gitconfig")
os.environ["GIT_TERMINAL_PROMPT"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# importado pelo caminho completo (files/painel/painel.py): é o nome que o teste de mutantes espera
import files.painel.painel as painel  # noqa: E402

sys.modules.setdefault("painel", painel)


@pytest.fixture
def p():
    return painel


@pytest.fixture(autouse=True)
def home_limpa():
    """Cada teste começa com ~/projetos vazio."""
    for item in _HOME.iterdir():
        if item.name in (".gitconfig",):
            continue
        shutil.rmtree(item) if item.is_dir() and not item.is_symlink() else item.unlink()
    (_HOME / "projetos").mkdir()
    yield _HOME


@pytest.fixture
def home():
    return _HOME


class Comandos:
    """Substitui painel.rodar: guarda os comandos e devolve respostas programadas."""

    def __init__(self):
        self.lista = []
        self.respostas = []  # (função que reconhece o comando, (código, saída))

    def responder(self, quando, codigo=0, saida=""):
        self.respostas.append((quando, (codigo, saida)))

    def __call__(self, cmd, cwd=None, timeout=120, entrada=None, so_saida=False):
        self.lista.append(list(cmd))
        for quando, r in self.respostas:
            if quando(cmd):
                return r
        return 0, ""

    def ultimo(self, comeca):
        for c in reversed(self.lista):
            if c[: len(comeca)] == comeca:
                return c
        return None


@pytest.fixture
def cmds(monkeypatch):
    c = Comandos()
    monkeypatch.setattr(painel, "rodar", c)
    monkeypatch.setattr(painel.time, "sleep", lambda s: None)
    return c


@pytest.fixture
def tarefas(monkeypatch):
    """Substitui iniciar_tarefa: devolve o comando que seria executado."""
    lista = []

    def falsa(ferramenta, titulo, cmd, cwd=None, env_extra=None):
        lista.append({"ferramenta": ferramenta, "titulo": titulo, "cmd": list(cmd), "cwd": cwd})
        return {"tarefa": "t", "titulo": titulo}

    monkeypatch.setattr(painel, "iniciar_tarefa", falsa)
    return lista
