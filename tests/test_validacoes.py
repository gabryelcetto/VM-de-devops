"""Validações de entrada (nomes, portas, memória, branch, cron, URL) e dicas de erro.
Cada regra tem casos nos dois lados do limite, para que qualquer mudança nela seja percebida."""
import pytest


@pytest.mark.parametrize("nome,ok", [
    ("a", True), ("meu-site", True), ("app_1.2", True), ("A" * 128, True),
    ("A" * 129, False), ("", False), ("-x", False), (".x", False), ("_x", False),
    ("a b", False), ("a/b", False), ("a;rm", False), ("..", False), ("a\n", False),
])
def test_nome_ok(p, nome, ok):
    assert bool(p.NOME_OK.match(nome)) is ok


@pytest.mark.parametrize("ref,ok", [
    ("nginx:alpine", True), ("ghcr.io/o/img:1.0", True), ("img@sha256:abc", True), ("a" * 255, True),
    ("a" * 256, False), ("nginx\n", False), ("-v", False), ("", False), ("a b", False), ("a$(x)", False),
])
def test_ref_ok(p, ref, ok):
    assert bool(p.REF_OK.match(ref)) is ok


@pytest.mark.parametrize("b,ok", [
    ("main", True), ("feature/teste", True), ("v1.0", True), ("a" * 100, True),
    ("a" * 101, False), ("main\n", False), ("-x", False), ("a..b", False), ("", False), ("a b", False), ("a~1", False),
])
def test_branch_ok(p, b, ok):
    assert bool(p.BRANCH_OK.match(b)) is ok


@pytest.mark.parametrize("porta,ok", [
    ("8081:80", True), ("1:1", True), ("53:53/udp", True), ("80:80/tcp", True), ("12345:12345", True),
    ("123456:80", False), ("80:80\n", False), ("80", False), ("80:80/sctp", False), (":80", False), ("a:80", False),
])
def test_portas_ok(p, porta, ok):
    assert bool(p.PORTAS_OK.match(porta)) is ok


@pytest.mark.parametrize("mem,ok", [
    ("512m", True), ("1g", True), ("1G", True), ("999999", True), ("100k", True),
    ("1000000", False), ("1g\n", False), ("1.5g", False), ("m", False), ("1t", False), ("", False),
])
def test_mem_ok(p, mem, ok):
    assert bool(p.MEM_OK.match(mem)) is ok


@pytest.mark.parametrize("cron,ok", [
    ("H/5 * * * *", True), ("@daily", True), ("H 8 * * 1-5", True), ("0 3 * * *", True),
    ("a" * 101, False), ("@daily\n", False), ("", False), ("$(id)", False), ("* * * * *;x", False),
])
def test_cron_ok(p, cron, ok):
    assert bool(p.CRON_OK.match(cron)) is ok


def test_json_linhas_ignora_lixo(p):
    txt = 'aviso: algo\n{"a": 1}\n  {"b": 2}  \n{quebrado\n\n'
    assert p.json_linhas(txt) == [{"a": 1}, {"b": 2}]
    assert p.json_linhas("") == []


def test_ok_ou_erro(p):
    assert p.ok_ou_erro((0, "tudo certo")) == "tudo certo"
    with pytest.raises(p.Erro, match="deu ruim"):
        p.ok_ou_erro((1, "deu ruim"))
    with pytest.raises(p.Erro, match="código 2"):
        p.ok_ou_erro((2, ""))


@pytest.mark.parametrize("saida,trecho", [
    ("Bind for 0.0.0.0:8081 failed: port is already allocated", "A porta já está sendo usada"),
    ('The container name "/meu-site" is already in use by container', "Já existe um container chamado meu-site"),
    ("git@github.com: Permission denied (publickey).", "O GitHub recusou a chave SSH"),
    ("fatal: could not read Username for 'https://github.com'", "O GitHub pediu login"),
    ("ERROR: Repository not found.", "Repositório não encontrado"),
    (" ! [rejected]        main -> main (fetch first)", "Faça Pull primeiro"),
    ("fatal: refusing to merge unrelated histories", "históricos"),
    ("There is no tracking information for the current branch.", "Faça Push primeiro"),
    ("CONFLICT (content): Merge conflict in a.txt", "Conflito"),
    ("fatal: destination path 'repo' already exists and is not an empty directory.", "Já existe a pasta repo"),
    ("error: src refspec main does not match any", "nenhum commit"),
    ("Please tell me who you are.", "Configure seu nome e e-mail"),
    ("script returned exit code 127", "Algum comando do script não existe"),
])
def test_dicas_para(p, saida, trecho):
    dicas = p.dicas_para(saida)
    assert len(dicas) >= 1
    assert any(trecho in d for d in dicas), dicas


def test_dicas_sem_erro_conhecido_e_sem_repetir(p):
    assert p.dicas_para("tudo certo") == []
    assert p.dicas_para(None) == []
    duas = "port is already allocated\naddress already in use"
    assert len(p.dicas_para(duas)) == 1  # a mesma dica não aparece duas vezes


def test_url_git(p):
    assert p._url_git(" https://github.com/gabryel/app.git ") == "https://github.com/gabryel/app.git"
    assert p._url_git("git@github.com:gabryel/app.git") == "git@github.com:gabryel/app.git"
    for ruim in ("", "http://github.com/a/b", "ftp://x/y", "https://github.com/a/b; rm -rf /", "file:///etc"):
        with pytest.raises(p.Erro, match="inválida"):
            p._url_git(ruim)
    with pytest.raises(p.Erro, match="usuario/repositorio"):
        p._url_git("https://github.com/usuario/repositorio.git")


def test_caminho_job(p):
    assert p.caminho_job("app") == "/job/app"
    assert p.caminho_job("pasta/meu job") == "/job/pasta/job/meu%20job"
    for ruim in ("", "a/../b", "x" * 201):
        with pytest.raises(p.Erro):
            p.caminho_job(ruim)
    assert p.caminho_job("x" * 200) == "/job/" + "x" * 200


def test_texto_erro_do_jenkins(p):
    html = ("<html><head><title>Jenkins</title></head><body><header>Dashboard Search</header>"
            "<h1>Erro</h1><p>A job already exists with the name &quot;app&quot;</p>"
            "<footer>Jenkins 2.500.1 REST API</footer></body></html>")
    assert p._texto_erro(html) == 'Erro A job already exists with the name "app"'
