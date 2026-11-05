"""Servidor HTTP do Painel: segurança (token e Host) e respostas de erro."""
import http.client
import json
import threading

import pytest


@pytest.fixture(scope="module")
def servidor():
    import painel
    srv = painel.ThreadingHTTPServer(("127.0.0.1", 0), painel.Handler)
    porta = srv.server_address[1]
    painel.HOSTS_OK.add(f"localhost:{porta}")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield porta
    srv.shutdown()


def pedir(porta, metodo, caminho, corpo=None, host=None, token=None, cab=None):
    c = http.client.HTTPConnection("127.0.0.1", porta, timeout=10)
    h = {"Host": host or f"localhost:{porta}"}
    if token is not None:
        h["X-Painel-Token"] = token
    h.update(cab or {})
    c.request(metodo, caminho, body=corpo, headers=h)
    r = c.getresponse()
    dados = r.read()
    c.close()
    return r.status, r.getheader("Content-Type"), dados, dict(r.getheaders())


def test_pagina_tem_token_e_cabecalhos_de_seguranca(p, servidor):
    st, tipo, corpo, cab = pedir(servidor, "GET", "/")
    assert st == 200 and tipo.startswith("text/html")
    assert p.TOKEN.encode() in corpo and b"__TOKEN__" not in corpo
    assert cab["X-Frame-Options"] == "DENY" and cab["X-Content-Type-Options"] == "nosniff" and cab["Cache-Control"] == "no-store"


def test_saude(servidor):
    st, _, corpo, _ = pedir(servidor, "GET", "/saude")
    assert st == 200 and json.loads(corpo) == {"ok": True}


@pytest.mark.parametrize("host", ["exemplo.com", "127.0.0.1:1", "localhost", "evil.localhost:18090"])
def test_host_errado_bloqueado(servidor, host):
    for metodo in ("GET", "POST"):
        st, _, corpo, _ = pedir(servidor, metodo, "/api/sistema", host=host, corpo=b"{}")
        assert st == 403 and "permitido só" in json.loads(corpo)["erro"]


def test_post_sem_token_ou_token_errado(p, servidor):
    for tok in (None, "", "x" * 32, p.TOKEN[:-1]):
        st, _, corpo, _ = pedir(servidor, "POST", "/api/arquivo", corpo=b'{"acao":"salvar","caminho":"~/x","conteudo":"x"}', token=tok)
        assert st == 403 and "Token inválido" in json.loads(corpo)["erro"]


def test_post_ok_e_erros(p, servidor, home):
    st, _, corpo, _ = pedir(servidor, "POST", "/api/arquivo", token=p.TOKEN,
                            corpo=json.dumps({"acao": "salvar", "caminho": "~/via-http.txt", "conteudo": "oi"}).encode())
    assert st == 200 and json.loads(corpo) == {"ok": True, "resultado": "Salvo: via-http.txt"}
    assert (home / "via-http.txt").read_text() == "oi"
    st, _, corpo, _ = pedir(servidor, "POST", "/api/arquivo", token=p.TOKEN, corpo=b'{"acao":"salvar","caminho":"/etc/x"}')
    assert st == 400 and "pasta pessoal" in json.loads(corpo)["erro"]
    st, _, _, _ = pedir(servidor, "POST", "/api/nao-existe", token=p.TOKEN, corpo=b"{}")
    assert st == 404


@pytest.mark.parametrize("corpo,msg", [(b"{quebrado", "JSON válido"), (b"[1, 2]", "objeto JSON"), (b'"texto"', "objeto JSON")])
def test_post_json_invalido_da_400(p, servidor, corpo, msg):
    st, _, r, _ = pedir(servidor, "POST", "/api/arquivo", token=p.TOKEN, corpo=corpo)
    assert st == 400 and msg in json.loads(r)["erro"]


def test_post_tamanho_invalido(p, servidor):
    for tam in ("-1", "abc", "2000001"):
        c = http.client.HTTPConnection("127.0.0.1", servidor, timeout=5)
        c.putrequest("POST", "/api/arquivo", skip_host=True)
        c.putheader("Host", f"localhost:{servidor}")
        c.putheader("X-Painel-Token", p.TOKEN)
        c.putheader("Content-Length", tam)
        c.endheaders()
        r = c.getresponse()
        assert r.status == 400, tam
        c.close()


def test_get_404_e_tarefa(servidor):
    st, _, _, _ = pedir(servidor, "GET", "/api/nao-existe")
    assert st == 404
    st, _, corpo, _ = pedir(servidor, "GET", "/api/tarefa?id=nada")
    assert st == 404 and "não encontrada" in json.loads(corpo)["erro"]


def test_get_erro_inesperado_vira_500_sem_derrubar(p, servidor, monkeypatch):
    def quebra():
        raise RuntimeError("bug")
    monkeypatch.setitem(p.GETS, "/api/teste-quebra", quebra)
    st, _, corpo, _ = pedir(servidor, "GET", "/api/teste-quebra")
    assert st == 500 and json.loads(corpo)["erro"] == "RuntimeError: bug"
    assert pedir(servidor, "GET", "/saude")[0] == 200
