"""Casos escritos a partir do teste de mutantes: cada um mata defeitos que os outros testes
deixavam passar (textos exatos, limites, valores padrão)."""
import http.client
import json
import threading
import time
import xml.etree.ElementTree as ET

import pytest


def msg(p, fn, *a):
    with pytest.raises(p.Erro) as e:
        fn(*a)
    return str(e.value)


# ---------------------------------------------------------------- arquivos
def test_arquivo_textos_exatos(p):
    assert msg(p, p.acao_arquivo, {"acao": "x"}) == "Ação desconhecida."
    assert msg(p, p.acao_arquivo, {"acao": "projeto", "nome": "a b"}) == "Nome inválido: use letras, números, - _ ."
    assert msg(p, p.acao_arquivo, {"acao": "projeto"}) == "Nome inválido: use letras, números, - _ ."


def test_arquivo_grande_texto_exato(p, home):
    (home / "g.txt").write_text("x" * 1_000_001)
    assert msg(p, p.acao_arquivo, {"acao": "ler", "caminho": "~/g.txt"}) == "Arquivo grande demais para editar aqui."


def test_ler_arquivo_com_bytes_invalidos(p, home):
    (home / "bin.txt").write_bytes(b"ok \xff\xfe fim")
    assert p.acao_arquivo({"acao": "ler", "caminho": "~/bin.txt"}) == "ok �� fim"


def test_salvar_cria_pastas_e_conteudo_padrao(p, home):
    p.acao_arquivo({"acao": "salvar", "caminho": "~/a/b/c/novo.txt"})
    assert (home / "a/b/c/novo.txt").read_text() == ""


def test_projeto_cria_projetos_e_subpastas(p, home):
    (home / "projetos").rmdir()
    r = p.acao_arquivo({"acao": "projeto", "nome": "vazio"})
    assert r == {"pasta": str(home / "projetos" / "vazio"), "msg": "Projeto criado em ~/projetos/vazio."}
    assert (home / "projetos" / "vazio").is_dir()
    p.acao_arquivo({"acao": "projeto", "nome": "fundo", "arquivos": {"src/a/b/c.py": "x"}})
    assert (home / "projetos/fundo/src/a/b/c.py").read_text() == "x"


# ---------------------------------------------------------------- validações com texto exato
def test_textos_exatos_de_validacao(p):
    assert msg(p, p.caminho_job, "") == "Job inválido."
    assert msg(p, p._url_git, None) == ("URL do repositório inválida (ex.: https://github.com/usuario/repo.git "
                                        "ou git@github.com:usuario/repo.git).")
    assert msg(p, p._url_git, "https://github.com/usuario/repositorio") == (
        "Troque o endereço de exemplo (usuario/repositorio) pelo endereço do seu repositório no GitHub.")
    assert msg(p, p.ver_tarefa, {}) == "Tarefa não encontrada."
    assert msg(p, p.dentro_da_home, "/etc") == "Só é permitido usar pastas dentro da sua pasta pessoal."


def test_dica_em_linha_do_meio(p):
    # "$" no fim de uma linha que não é a última: só funciona com re.M
    assert p.dicas_para("sh: app: not found\noutra linha") == [
        "Algum comando do script não existe na máquina. Confira a digitação ou instale o programa."]


def test_gatilhos_xml_exato(p):
    raiz = p._gatilhos(ET.Element("x"), {"cron_scm": "H/5 * * * *", "cron": "@daily"})
    assert [(t.tag, [(e.tag, e.text) for e in t]) for t in raiz] == [
        ("hudson.triggers.SCMTrigger", [("spec", "H/5 * * * *"), ("ignorePostCommitHooks", "false")]),
        ("hudson.triggers.TimerTrigger", [("spec", "@daily")])]
    assert msg(p, p._gatilhos, ET.Element("x"), {"cron": "a;b"}) == "Horário inválido: a;b (ex.: H/5 * * * *)"


# ---------------------------------------------------------------- tarefas
def test_ver_tarefa_desde_invalido_ou_negativo(p):
    r = p.iniciar_tarefa("t", "eco", ["sh", "-c", "echo um; echo dois; echo tres"])
    for _ in range(100):
        t = p.ver_tarefa({"id": [r["tarefa"]]})
        if t["fim"]:
            break
        time.sleep(0.05)
    assert t["linhas"] == ["um", "dois", "tres"]
    assert p.ver_tarefa({"id": [r["tarefa"]], "desde": ["abc"]})["linhas"] == ["um", "dois", "tres"]
    assert p.ver_tarefa({"id": [r["tarefa"]], "desde": ["-2"]})["linhas"] == ["um", "dois", "tres"]
    assert p.ver_tarefa({"id": [r["tarefa"]], "desde": ["1"]})["linhas"] == ["dois", "tres"]


# ---------------------------------------------------------------- servidor HTTP
@pytest.fixture(scope="module")
def srv():
    import painel
    s = painel.ThreadingHTTPServer(("127.0.0.1", 0), painel.Handler)
    porta = s.server_address[1]
    painel.HOSTS_OK.add(f"localhost:{porta}")
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield porta
    s.shutdown()


def post(porta, caminho, corpo=None, token=None, host=None, tamanho=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    c.putrequest("POST", caminho, skip_host=True, skip_accept_encoding=True)
    if host is not False:
        c.putheader("Host", host or f"localhost:{porta}")
    if token:
        c.putheader("X-Painel-Token", token)
    if tamanho is not None:
        c.putheader("Content-Length", tamanho)
    elif corpo is not None:
        c.putheader("Content-Length", str(len(corpo)))
    c.endheaders()
    if corpo:
        c.send(corpo)
    r = c.getresponse()
    dados = json.loads(r.read())
    c.close()
    return r.status, dados


def test_post_sem_corpo_e_aceito(p, srv):
    assert post(srv, "/api/tarefa-parar", token=p.TOKEN) == (200, {"ok": True, "resultado": "A tarefa já terminou."})
    assert post(srv, "/api/tarefa-parar", b"", token=p.TOKEN, tamanho="0") == (200, {"ok": True, "resultado": "A tarefa já terminou."})


def test_post_no_limite_de_tamanho(p, srv):
    corpo = b'{"x": "' + b"a" * (2_000_000 - 9) + b'"}'
    assert len(corpo) == 2_000_000
    assert post(srv, "/api/tarefa-parar", corpo, token=p.TOKEN)[0] == 200
    assert post(srv, "/api/tarefa-parar", token=p.TOKEN, tamanho="2000001") == (400, {"erro": "Dados grandes demais."})
    assert post(srv, "/api/tarefa-parar", token=p.TOKEN, tamanho="-1") == (400, {"erro": "Pedido inválido."})
    assert post(srv, "/api/tarefa-parar", token=p.TOKEN, tamanho="abc") == (400, {"erro": "Pedido inválido."})


def test_post_textos_exatos(p, srv):
    assert post(srv, "/api/nada", b"{}", token=p.TOKEN) == (404, {"erro": "não encontrado"})
    assert post(srv, "/api/arquivo", b"{}", token="errado") == (403, {"erro": "Token inválido. Recarregue a página do painel."})
    assert post(srv, "/api/arquivo", b"{}", token=p.TOKEN, host="x.com") == (403, {"erro": f"Acesso permitido só por http://localhost:{p.PORTA}"})


def test_host_errado_nao_executa_nada(p, srv, home):
    corpo = json.dumps({"acao": "salvar", "caminho": "~/invasao.txt", "conteudo": "x"}).encode()
    assert post(srv, "/api/arquivo", corpo, token=p.TOKEN, host="evil.com")[0] == 403
    assert post(srv, "/api/arquivo", corpo, token=p.TOKEN, host=False)[0] == 403  # pedido sem Host
    time.sleep(0.2)
    assert not (home / "invasao.txt").exists()
