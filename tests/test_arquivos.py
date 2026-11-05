"""Segurança de caminhos e arquivos: nada pode sair da pasta pessoal do aluno."""
import os

import pytest


def test_dentro_da_home_aceita_home_e_subpastas(p, home):
    assert p.dentro_da_home(str(home)) == home
    assert p.dentro_da_home("~/projetos/app") == home / "projetos" / "app"
    assert p.dentro_da_home(str(home / "a" / ".." / "b")) == home / "b"


@pytest.mark.parametrize("ruim", ["/etc/passwd", "/", "~/../", "~/../../etc", "/tmp", "/home"])
def test_dentro_da_home_recusa_fora(p, ruim):
    with pytest.raises(p.Erro, match="pasta pessoal"):
        p.dentro_da_home(ruim)


def test_dentro_da_home_recusa_atalho_para_fora(p, home):
    os.symlink("/etc", home / "projetos" / "atalho")
    with pytest.raises(p.Erro):
        p.dentro_da_home(str(home / "projetos" / "atalho" / "passwd"))


def test_dentro_da_home_recusa_pasta_com_nome_parecido(p, home):
    # /home/aluno-outro não está dentro de /home/aluno
    with pytest.raises(p.Erro):
        p.dentro_da_home(str(home) + "-outro/x")


def test_arquivo_permitido(p, home):
    assert str(p.arquivo_permitido("/opt/aula/docker-compose.yml")).startswith("/opt/")
    assert p.arquivo_permitido("~/x.yml") == home / "x.yml"
    for ruim in ("/etc/x.yml", "/opt", "/optar/x.yml", "/opt/../etc/x.yml"):
        with pytest.raises(p.Erro):
            p.arquivo_permitido(ruim)


def test_salvar_e_ler_com_copia(p, home):
    assert p.acao_arquivo({"acao": "salvar", "caminho": "~/notas/a.txt", "conteudo": "um"}) == "Salvo: a.txt"
    p.acao_arquivo({"acao": "salvar", "caminho": "~/notas/a.txt", "conteudo": "dois"})
    assert p.acao_arquivo({"acao": "ler", "caminho": "~/notas/a.txt"}) == "dois"
    assert (home / "notas" / "a.txt.bak").read_text() == "um"
    assert p.acao_arquivo({"acao": "ler", "caminho": "~/nao-existe.txt"}) == ""


def test_ler_arquivo_grande_demais(p, home):
    (home / "grande.txt").write_text("x" * 1_000_001)
    with pytest.raises(p.Erro, match="grande demais"):
        p.acao_arquivo({"acao": "ler", "caminho": "~/grande.txt"})
    (home / "limite.txt").write_text("x" * 1_000_000)
    assert len(p.acao_arquivo({"acao": "ler", "caminho": "~/limite.txt"})) == 1_000_000


def test_salvar_fora_da_home_recusado(p):
    with pytest.raises(p.Erro):
        p.acao_arquivo({"acao": "salvar", "caminho": "/tmp/x.txt", "conteudo": "x"})


def test_projeto_cria_arquivos(p, home, cmds):
    r = p.acao_arquivo({"acao": "projeto", "nome": "app", "git": True,
                        "arquivos": {"main.tf": "a", "src/app.py": "b"}})
    assert r["pasta"] == str(home / "projetos" / "app")
    assert (home / "projetos" / "app" / "src" / "app.py").read_text() == "b"
    assert cmds.ultimo(["git", "init"]) == ["git", "init", "-q", "-b", "main", str(home / "projetos" / "app")]


def test_projeto_sem_git_nao_roda_git(p, cmds):
    p.acao_arquivo({"acao": "projeto", "nome": "vazio"})
    assert cmds.lista == []


def test_projeto_recusa_caminho_para_fora(p, home):
    with pytest.raises(p.Erro, match="Caminho de arquivo inválido"):
        p.acao_arquivo({"acao": "projeto", "nome": "app", "arquivos": {"../fora.txt": "x"}})
    assert not (home / "projetos" / "fora.txt").exists()
    with pytest.raises(p.Erro, match="Caminho de arquivo inválido"):
        p.acao_arquivo({"acao": "projeto", "nome": "app2", "arquivos": {"/etc/x": "x"}})


def test_projeto_nome_invalido_e_repetido(p, home):
    for ruim in ("", "../x", "a b", "-a"):
        with pytest.raises(p.Erro, match="Nome inválido"):
            p.acao_arquivo({"acao": "projeto", "nome": ruim})
    p.acao_arquivo({"acao": "projeto", "nome": "app", "arquivos": {"a": "1"}})
    with pytest.raises(p.Erro, match="Já existe"):
        p.acao_arquivo({"acao": "projeto", "nome": "app", "arquivos": {"b": "2"}})
    (home / "projetos" / "vazia").mkdir()  # pasta vazia pode ser reaproveitada
    p.acao_arquivo({"acao": "projeto", "nome": "vazia", "arquivos": {"a": "1"}})


def test_arquivo_acao_desconhecida(p):
    with pytest.raises(p.Erro, match="desconhecida"):
        p.acao_arquivo({"acao": "apagar"})


def test_abrir_url_permitida_e_bloqueada(p, monkeypatch):
    abertos = []
    monkeypatch.setattr(p, "lancar", lambda cmd, cwd=None: abertos.append(cmd))
    p.acao_abrir({"acao": "url", "url": "http://localhost:3000/d/esta-vm"})
    p.acao_abrir({"acao": "url", "url": "https://github.com/settings/keys"})
    assert abertos == [["firefox", "http://localhost:3000/d/esta-vm"], ["firefox", "https://github.com/settings/keys"]]
    for ruim in ("http://exemplo.com", "https://github.com.mal.com/x", "javascript:alert(1)",
                 "http://localhost:3000\nx", "file:///etc/passwd", "http://localhost/"):
        with pytest.raises(p.Erro, match="não permitido"):
            p.acao_abrir({"acao": "url", "url": ruim})


def test_abrir_novo_arquivo(p, home, monkeypatch):
    abertos = []
    monkeypatch.setattr(p, "lancar", lambda cmd, cwd=None: abertos.append(cmd))
    p.acao_abrir({"acao": "novo_arquivo", "caminho": "~/projetos", "nome": "app.py", "conteudo": "print(1)"})
    assert (home / "projetos" / "app.py").read_text() == "print(1)"
    p.acao_abrir({"acao": "novo_arquivo", "caminho": "~/projetos", "nome": "app.py", "conteudo": "outro"})
    assert (home / "projetos" / "app.py").read_text() == "print(1)"  # não sobrescreve
    for ruim in ("../x", "a/b", "", "..", "."):
        with pytest.raises(p.Erro, match="inválido"):
            p.acao_abrir({"acao": "novo_arquivo", "caminho": "~/projetos", "nome": ruim})


def test_abrir_comandos_exatos(p, home, monkeypatch):
    abertos = []
    monkeypatch.setattr(p, "lancar", lambda cmd, cwd=None: abertos.append(cmd))
    (home / "projetos" / "app").mkdir()
    (home / "projetos" / "app" / "a.py").write_text("")
    assert p.acao_abrir({"acao": "url", "url": "http://127.0.0.1:8080/job/x"}) == "Abrindo no navegador."
    assert p.acao_abrir({"acao": "vscode", "caminho": "~/projetos/app"}) == "Abrindo no VS Code."
    assert p.acao_abrir({"acao": "vscode"}) == "Abrindo no VS Code."  # sem caminho: ~/projetos
    assert p.acao_abrir({"acao": "terminal", "caminho": "~/projetos/app/a.py"}) == "Abrindo o terminal."
    assert p.acao_abrir({"acao": "pasta", "caminho": "~/projetos/app"}) == "Abrindo a pasta."
    assert p.acao_abrir({"acao": "pasta", "caminho": "~/projetos/app/a.py"}) == "Abrindo a pasta."
    assert p.acao_abrir({"acao": "novo_arquivo", "caminho": "~/projetos/app", "nome": " b.py "}) == "Abrindo b.py no VS Code."
    app = str(home / "projetos" / "app")
    assert abertos == [["firefox", "http://127.0.0.1:8080/job/x"], ["code", app], ["code", str(home / "projetos")],
                       ["xfce4-terminal", f"--working-directory={app}"], ["thunar", app], ["thunar", app],
                       ["code", app, app + "/b.py"]]
    assert (home / "projetos" / "app" / "b.py").read_text() == ""


def test_abrir_mensagens_exatas(p):
    for d, msg in (({"acao": "url", "url": "http://x.com"}, "Endereço não permitido."), ({"acao": "url"}, "Endereço não permitido."),
                   ({"acao": "novo_arquivo", "nome": "a/b"}, "Nome de arquivo inválido."), ({"acao": "novo_arquivo"}, "Nome de arquivo inválido."),
                   ({"acao": "explodir"}, "Ação desconhecida.")):
        with pytest.raises(p.Erro) as e:
            p.acao_abrir(d)
        assert str(e.value) == msg
