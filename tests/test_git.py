"""Aba Git: roda o git de verdade em repositórios temporários."""
import subprocess

import pytest


@pytest.fixture
def repo(p, home):
    p.acao_git({"acao": "configurar", "nome": "Aluno Teste", "email": "aluno@lab.local"})
    p.acao_git({"acao": "novo", "nome": "app"})
    r = home / "projetos" / "app"
    return r


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).stdout.strip()


def test_configurar_identidade(p):
    assert p.acao_git({"acao": "configurar", "nome": " Ana ", "email": "ana@x.com"}) == "Identidade do Git salva."
    assert subprocess.run(["git", "config", "--global", "user.name"], capture_output=True, text=True).stdout.strip() == "Ana"
    for ruim in ({"nome": "", "email": "a@b"}, {"nome": "A", "email": "sem-arroba"}, {"nome": "A", "email": "a@b@c"},
                 {"nome": "A", "email": "a b@c"}):
        with pytest.raises(p.Erro, match="e-mail válido"):
            p.acao_git({"acao": "configurar", **ruim})


def test_novo_repositorio(p, repo):
    assert (repo / ".git").is_dir() and (repo / "README.md").read_text() == "# app\n"
    assert git(repo, "branch", "--show-current") == "main"
    with pytest.raises(p.Erro, match="Já existe"):
        p.acao_git({"acao": "novo", "nome": "app"})
    with pytest.raises(p.Erro, match="Nome inválido"):
        p.acao_git({"acao": "novo", "nome": "../fora"})


def test_commit_de_arquivos_escolhidos(p, repo):
    (repo / "a.txt").write_text("a")
    (repo / "b.txt").write_text("b")
    p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "só o a", "arquivos": ["a.txt"]})
    assert git(repo, "log", "--format=%s") == "só o a"
    assert git(repo, "show", "--name-only", "--format=") == "a.txt"
    p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "o resto"})
    assert git(repo, "status", "--porcelain") == ""


def test_commit_recusas(p, repo):
    with pytest.raises(p.Erro, match="mensagem"):
        p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "  "})
    with pytest.raises(p.Erro, match="fora do repositório"):
        p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "x", "arquivos": ["../../segredo"]})


def test_commit_sem_mudancas_explica(p, repo):
    p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "primeiro"})
    with pytest.raises(p.Erro, match="nothing to commit|nada a submeter|nada para"):
        p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "de novo"})


def test_branch_merge_tag_e_apagar(p, repo):
    p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "base"})
    assert p.acao_git({"acao": "checkout", "repo": str(repo), "branch": "feature/x"}) is not None
    assert git(repo, "branch", "--show-current") == "feature/x"
    (repo / "x.txt").write_text("x")
    p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "na branch"})
    p.acao_git({"acao": "checkout", "repo": str(repo), "branch": "main"})
    with pytest.raises(p.Erro, match="^NAO_JUNTADA"):
        p.acao_git({"acao": "apagar_branch", "repo": str(repo), "branch": "feature/x"})
    p.acao_git({"acao": "merge", "repo": str(repo), "branch": "feature/x"})
    assert (repo / "x.txt").exists()
    assert p.acao_git({"acao": "apagar_branch", "repo": str(repo), "branch": "feature/x"}) == "Branch feature/x apagada."
    assert p.acao_git({"acao": "tag", "repo": str(repo), "tag": "v1.0.0"}).startswith("Tag v1.0.0 criada")
    assert git(repo, "tag") == "v1.0.0"
    info = p.acao_git({"acao": "info_repo", "repo": str(repo)})
    assert info["tags"] == ["v1.0.0"] and info["stashes"] == []
    assert "na branch" in p.acao_git({"acao": "grafico", "repo": str(repo)})


def test_apagar_branch_forcado(p, repo):
    p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "base"})
    p.acao_git({"acao": "checkout", "repo": str(repo), "branch": "lixo"})
    (repo / "l.txt").write_text("l")
    p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "lixo"})
    p.acao_git({"acao": "checkout", "repo": str(repo), "branch": "main"})
    p.acao_git({"acao": "apagar_branch", "repo": str(repo), "branch": "lixo", "forcar": True})
    assert "lixo" not in git(repo, "branch")


def test_merge_com_conflito(p, repo):
    (repo / "c.txt").write_text("base\n")
    p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "base"})
    p.acao_git({"acao": "checkout", "repo": str(repo), "branch": "outra"})
    (repo / "c.txt").write_text("outra\n")
    p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "outra"})
    p.acao_git({"acao": "checkout", "repo": str(repo), "branch": "main"})
    (repo / "c.txt").write_text("main\n")
    p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "main"})
    with pytest.raises(p.Erro, match="Conflito no merge"):
        p.acao_git({"acao": "merge", "repo": str(repo), "branch": "outra"})


@pytest.mark.parametrize("acao", ["merge", "apagar_branch", "checkout"])
def test_branch_invalida(p, repo, acao):
    with pytest.raises(p.Erro, match="nválid"):
        p.acao_git({"acao": acao, "repo": str(repo), "branch": "-D main"})


def test_desfazer_commit(p, repo):
    p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "um"})
    with pytest.raises(p.Erro, match="só tem um commit"):
        p.acao_git({"acao": "desfazer_commit", "repo": str(repo)})
    (repo / "d.txt").write_text("d")
    p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "dois"})
    p.acao_git({"acao": "desfazer_commit", "repo": str(repo)})
    assert git(repo, "log", "--format=%s") == "um" and (repo / "d.txt").exists()


def test_stash(p, repo):
    p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "um"})
    (repo / "s.txt").write_text("s")
    p.acao_git({"acao": "stash", "repo": str(repo)})
    assert not (repo / "s.txt").exists()
    p.acao_git({"acao": "stash_pop", "repo": str(repo)})
    assert (repo / "s.txt").exists()


def test_descartar(p, repo):
    (repo / "m.txt").write_text("original")
    p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "um"})
    (repo / "m.txt").write_text("mudado")
    (repo / "novo.txt").write_text("novo")
    p.acao_git({"acao": "descartar", "repo": str(repo), "arquivo": "m.txt"})
    assert (repo / "m.txt").read_text() == "original"
    p.acao_git({"acao": "descartar", "repo": str(repo), "arquivo": "novo.txt", "novo": True})
    assert not (repo / "novo.txt").exists()
    for ruim in ("../fora.txt", ""):
        with pytest.raises(p.Erro, match="Arquivo inválido"):
            p.acao_git({"acao": "descartar", "repo": str(repo), "arquivo": ruim})


def test_diff(p, repo):
    p.acao_git({"acao": "commit", "repo": str(repo), "mensagem": "um"})
    assert p.acao_git({"acao": "diff", "repo": str(repo)}) == "(sem diferenças)"
    (repo / "README.md").write_text("# mudou\n")
    d = p.acao_git({"acao": "diff", "repo": str(repo)})
    assert "README.md" in d and "+# mudou" in d


def test_remoto(p, repo):
    p.acao_git({"acao": "remoto", "repo": str(repo), "url": "https://github.com/gabryel/app.git"})
    p.acao_git({"acao": "remoto", "repo": str(repo), "url": "git@github.com:gabryel/app2.git"})
    assert git(repo, "config", "--get", "remote.origin.url") == "git@github.com:gabryel/app2.git"
    with pytest.raises(p.Erro, match="URL inválida"):
        p.acao_git({"acao": "remoto", "repo": str(repo), "url": "https://x/y; rm -rf /"})


def test_nao_e_repositorio(p, home):
    (home / "projetos" / "solta").mkdir()
    with pytest.raises(p.Erro, match="não é um repositório"):
        p.acao_git({"acao": "commit", "repo": str(home / "projetos" / "solta"), "mensagem": "x"})
    with pytest.raises(p.Erro, match="pasta pessoal"):
        p.acao_git({"acao": "commit", "repo": "/etc", "mensagem": "x"})


def test_git_acao_desconhecida(p, repo):
    with pytest.raises(p.Erro, match="desconhecida"):
        p.acao_git({"acao": "rebase", "repo": str(repo)})


def test_token_validacao(p, cmds):
    with pytest.raises(p.Erro, match="token válido"):
        p.acao_git({"acao": "salvar_token", "usuario": "gabryel", "token": "curto"})
    with pytest.raises(p.Erro, match="token válido"):
        p.acao_git({"acao": "salvar_token", "usuario": "nome com espaço", "token": "ghp_" + "a" * 36})
    with pytest.raises(p.Erro, match="horas"):
        p.acao_git({"acao": "salvar_token", "usuario": "gabryel", "token": "ghp_" + "a" * 36, "horas": "muitas"})
    r = p.acao_git({"acao": "salvar_token", "usuario": "gabryel", "token": "ghp_" + "a" * 36, "horas": 99})
    assert "24 h" in r
    assert ["git", "config", "--global", "credential.helper", "cache --timeout=86400"] in cmds.lista
    r = p.acao_git({"acao": "salvar_token", "usuario": "gabryel", "token": "ghp_" + "a" * 36, "horas": 0})
    assert "8 h" in r  # 0/vazio usa o padrão de 8 h


def test_gerar_chave(p, home, cmds):
    with pytest.raises(p.Erro, match="E-mail inválido"):
        p.acao_git({"acao": "gerar_chave", "email": "sem-arroba"})
    p.acao_git({"acao": "gerar_chave", "email": "a@b.c"})
    assert cmds.lista[-1][:3] == ["ssh-keygen", "-t", "ed25519"] and "a@b.c" in cmds.lista[-1]
    (home / ".ssh" / "id_ed25519").write_text("chave")
    with pytest.raises(p.Erro, match="já tem uma chave"):
        p.acao_git({"acao": "gerar_chave", "email": "a@b.c"})
    p.acao_git({"acao": "gerar_chave", "email": "a@b.c", "substituir": True})
    assert not (home / ".ssh" / "id_ed25519").exists()  # a antiga é apagada antes de gerar


def test_testar_github(p, cmds):
    cmds.responder(lambda c: c[0] == "ssh", 1, "Hi gabryel! You've successfully authenticated, but GitHub does not provide shell access.")
    assert p.acao_git({"acao": "testar_github"}).startswith("✔ Conectado")
    cmds.respostas.clear()
    cmds.responder(lambda c: c[0] == "ssh", 255, "git@github.com: Permission denied (publickey).")
    with pytest.raises(p.Erro, match="recusou a chave"):
        p.acao_git({"acao": "testar_github"})
    cmds.respostas.clear()
    cmds.responder(lambda c: c[0] == "ssh", 255, "ssh: connect to host github.com port 22: Network is unreachable")
    with pytest.raises(p.Erro, match="Não foi possível falar"):
        p.acao_git({"acao": "testar_github"})
