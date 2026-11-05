"""Aba Docker: o comando montado para o docker precisa ser exatamente o esperado."""
import pytest


def _run(p, cmds, **d):
    p.acao_docker({"acao": "run", **d})
    return cmds.ultimo(["docker", "run"])


def test_run_completo(p, cmds, home):
    c = _run(p, cmds, imagem="nginx:alpine", nome="site", portas="8081:80, 8443:443/tcp", memoria="256m",
             env="A=1\nB=x=y\n", cpus="0.5", rede="minha-rede", reiniciar=True, volumes="dados:/data;~/site:/usr/share/nginx/html:ro")
    assert c == ["docker", "run", "-d",
                 "-v", "dados:/data", "-v", f"{home}/site:/usr/share/nginx/html:ro",
                 "--name", "site", "-p", "8081:80", "-p", "8443:443/tcp",
                 "--memory", "256m", "--memory-swap", "256m", "-e", "A=1", "-e", "B=x=y",
                 "--cpus", "0.5", "--network", "minha-rede", "--restart", "unless-stopped", "nginx:alpine"]


def test_run_minimo(p, cmds):
    assert _run(p, cmds, imagem=" nginx:alpine ") == ["docker", "run", "-d", "nginx:alpine"]


@pytest.mark.parametrize("img", ["python:3.12-slim", "ubuntu", "docker.io/library/alpine:latest", "node@sha256:abc"])
def test_imagem_base_fica_ligada(p, cmds, img):
    c = _run(p, cmds, imagem=img)
    assert c[-3:] == [img, "sleep", "infinity"]


def test_imagem_base_com_comando_proprio(p, cmds):
    c = _run(p, cmds, imagem="python:3.12-slim", comando='python -c "print(1)"')
    assert c[-4:] == ["python:3.12-slim", "python", "-c", "print(1)"]


def test_comando_com_aspas_quebradas_da_erro_claro(p, cmds):
    with pytest.raises(p.Erro, match="aspas"):
        _run(p, cmds, imagem="alpine", comando='echo "oi')


@pytest.mark.parametrize("campo,valor,msg", [
    ("imagem", "", "Informe a imagem"), ("imagem", "-v /:/x", "Informe a imagem"),
    ("nome", "meu site", "Nome inválido"), ("portas", "80", "Porta inválida"), ("portas", "70000:80", "Porta inválida"),
    ("portas", "0:80", "Porta inválida"), ("memoria", "1t", "Memória inválida"), ("env", "=x", "Variável inválida"),
    ("env", "SEM_IGUAL", "Variável inválida"), ("cpus", "1,5", "CPUs inválido"), ("cpus", "100", "CPUs inválido"),
    ("rede", "a b", "Rede inválida"), ("volumes", "dados", "Volume inválido"), ("volumes", "a b:/x", "Volume inválido"),
    ("volumes", "/etc:/x", "Volume inválido"),
])
def test_run_recusa(p, cmds, campo, valor, msg):
    d = {"imagem": "nginx:alpine", campo: valor}
    with pytest.raises(p.Erro, match=msg):
        p.acao_docker({"acao": "run", **d})
    assert cmds.ultimo(["docker", "run"]) is None


def test_volume_da_home_nao_escapa(p, cmds):
    for ruim in ("/home/../etc:/x", "~/../../etc:/x"):
        with pytest.raises(p.Erro):
            _run(p, cmds, imagem="alpine", volumes=ruim)


def test_run_erro_mostra_dica(p, cmds):
    cmds.responder(lambda c: c[:2] == ["docker", "run"], 125, "Bind for 0.0.0.0:8081 failed: port is already allocated")
    with pytest.raises(p.Erro, match="A porta já está sendo usada"):
        _run(p, cmds, imagem="nginx:alpine", portas="8081:80")


def test_run_erro_sem_dica_mostra_saida(p, cmds):
    cmds.responder(lambda c: c[:2] == ["docker", "run"], 125, "erro estranho")
    with pytest.raises(p.Erro, match="erro estranho"):
        _run(p, cmds, imagem="nginx:alpine")


CID = "a" * 64


def test_run_container_que_termina_bem(p, cmds):
    cmds.responder(lambda c: c[:2] == ["docker", "run"], 0, "baixando...\n" + CID)
    cmds.responder(lambda c: c[:2] == ["docker", "inspect"], 0, "exited 0")
    cmds.responder(lambda c: c[:2] == ["docker", "logs"], 0, "ola")
    r = p.acao_docker({"acao": "run", "imagem": "minha-img", "nome": "x"})
    assert "terminou com sucesso" in r and r.endswith("ola")
    assert cmds.ultimo(["docker", "inspect"])[-1] == CID[:12]


def test_run_container_que_quebra(p, cmds):
    cmds.responder(lambda c: c[:2] == ["docker", "run"], 0, CID)
    cmds.responder(lambda c: c[:2] == ["docker", "inspect"], 0, "exited 127")
    cmds.responder(lambda c: c[:2] == ["docker", "logs"], 0, "sh: app: command not found")
    with pytest.raises(p.Erro, match=r"parou com erro \(código 127\)") as e:
        p.acao_docker({"acao": "run", "imagem": "minha-img"})
    assert "Algum comando do script não existe" in str(e.value)


def test_run_rodando(p, cmds):
    cmds.responder(lambda c: c[:2] == ["docker", "run"], 0, CID)
    cmds.responder(lambda c: c[:2] == ["docker", "inspect"], 0, "running 0")
    assert p.acao_docker({"acao": "run", "imagem": "nginx:alpine", "nome": "site"}) == "Container site criado e rodando."
    r = p.acao_docker({"acao": "run", "imagem": "alpine"})
    assert r.startswith(f"Container {CID[:12]} criado e rodando.") and "sleep infinity" in r


@pytest.mark.parametrize("acao,esperado,msg", [
    ("start", ["docker", "start", "web"], "Container iniciado."), ("stop", ["docker", "stop", "web"], "Container parado."),
    ("restart", ["docker", "restart", "web"], "Container reiniciado."), ("rm", ["docker", "rm", "-f", "web"], "Container apagado."),
])
def test_acoes_de_container(p, cmds, acao, esperado, msg):
    assert p.acao_docker({"acao": acao, "container": "web"}) == msg
    assert cmds.lista[-1] == esperado


@pytest.mark.parametrize("acao", ["start", "stop", "restart", "rm", "logs", "terminal", "inspecionar", "exec"])
def test_container_invalido(p, cmds, acao):
    with pytest.raises(p.Erro):
        p.acao_docker({"acao": acao, "container": "-f; rm", "comando": "ls"})
    assert cmds.lista == []


def test_logs_exec_inspecionar(p, cmds):
    assert p.acao_docker({"acao": "logs", "container": "web"}) == "(sem logs)"
    assert cmds.lista[-1] == ["docker", "logs", "--tail", "300", "--timestamps", "web"]
    cmds.responder(lambda c: c[:2] == ["docker", "exec"], 2, "falhou")
    assert p.acao_docker({"acao": "exec", "container": "web", "comando": " ls "}) == "falhou\n\n[terminou com código 2]"
    assert cmds.lista[-1] == ["docker", "exec", "web", "sh", "-c", "ls"]
    with pytest.raises(p.Erro, match="Informe"):
        p.acao_docker({"acao": "exec", "container": "web", "comando": "  "})


def test_exec_sem_saida(p, cmds):
    assert p.acao_docker({"acao": "exec", "container": "web", "comando": "true"}) == "(sem saída)"


@pytest.mark.parametrize("acao,cmd", [
    ("volume_criar", ["docker", "volume", "create", "v1"]), ("volume_rm", ["docker", "volume", "rm", "v1"]),
    ("rede_criar", ["docker", "network", "create", "v1"]), ("rede_rm", ["docker", "network", "rm", "v1"]),
])
def test_volumes_e_redes(p, cmds, acao, cmd):
    assert "v1" in p.acao_docker({"acao": acao, "nome": " v1 "})
    assert cmds.lista[-1] == cmd
    with pytest.raises(p.Erro):
        p.acao_docker({"acao": acao, "nome": "a b"})


def test_imagens(p, cmds):
    assert p.acao_docker({"acao": "rmi", "imagem": "nginx:alpine"}) == "Imagem apagada."
    assert cmds.lista[-1] == ["docker", "rmi", "nginx:alpine"]
    p.acao_docker({"acao": "pull", "imagem": " alpine "})
    assert cmds.lista[-1] == ["docker", "pull", "alpine"]
    for acao in ("rmi", "pull"):
        with pytest.raises(p.Erro):
            p.acao_docker({"acao": acao, "imagem": "a b"})


def test_ligar_desligar(p, cmds):
    assert p.acao_docker({"acao": "ligar"}) == "Docker ligado."
    assert cmds.lista[-1] == ["systemctl", "start", "docker.socket", "docker.service"]
    assert p.acao_docker({"acao": "desligar"}).startswith("Docker desligado.")
    assert cmds.lista[-1] == ["systemctl", "stop", "docker.socket", "docker.service"]
    cmds.responder(lambda c: c[0] == "systemctl", 1, "sem permissão")
    with pytest.raises(p.Erro, match="sem permissão"):
        p.acao_docker({"acao": "ligar"})


def test_sugestao_de_porta_e_nome(p, cmds):
    cmds.responder(lambda c: c[:3] == ["docker", "image", "inspect"], 0, '{"80/tcp":{},"443/tcp":{},"x/tcp":{}}')
    cmds.responder(lambda c: c[:3] == ["docker", "ps", "-a"], 0, "0.0.0.0:8100->80/tcp\n0.0.0.0:8101->80/tcp")
    cmds.responder(lambda c: c[:2] == ["docker", "inspect"] and c[2] == "meu_site-1", 0, "[]")
    cmds.responder(lambda c: c[:2] == ["docker", "inspect"], 1, "No such object")
    r = p.acao_docker({"acao": "sugestao", "imagem": "gabryel/Meu_Site:1.0"})
    assert r == {"portas": "8102:80,8103:443", "nome": "meu_site-2"}
    cmds.respostas.clear()
    cmds.responder(lambda c: c[:2] == ["docker", "inspect"] and c[2] in ("site-1", "site-2"), 0, "[]")
    cmds.responder(lambda c: c[:2] == ["docker", "inspect"], 1, "No such object")
    assert p.acao_docker({"acao": "sugestao", "imagem": "site"})["nome"] == "site-3"
    assert p.acao_docker({"acao": "sugestao", "imagem": "site"})["portas"] == ""


def test_compose_salvar(p, cmds, home):
    r = p.acao_docker({"acao": "compose_salvar", "arquivo": "~/projetos/app/docker-compose.yml", "conteudo": "services: {}\n"})
    assert "Salvo" in r and (home / "projetos/app/docker-compose.yml").read_text() == "services: {}\n"
    assert not list((home / "projetos/app").glob(".*.painel"))
    with pytest.raises(p.Erro, match="precisa se chamar"):
        p.acao_docker({"acao": "compose_salvar", "arquivo": "~/projetos/app/x.yml", "conteudo": ""})


def test_compose_salvar_com_erro_nao_salva(p, cmds, home, monkeypatch):
    monkeypatch.setattr(p, "docker_ligado", lambda: True)
    cmds.responder(lambda c: "config" in c, 1, "yaml: line 1: did not find expected key")
    with pytest.raises(p.Erro, match="NÃO foi salvo"):
        p.acao_docker({"acao": "compose_salvar", "arquivo": "~/projetos/app/compose.yaml", "conteudo": "a: [b"})
    assert not (home / "projetos/app/compose.yaml").exists()


def test_compose_up_down_ver(p, cmds, home):
    arq = home / "projetos/app/docker-compose.yml"
    arq.parent.mkdir(parents=True)
    arq.write_text("services: {}\n")
    assert p.acao_docker({"acao": "compose_ver", "arquivo": str(arq)}) == "services: {}\n"
    p.acao_docker({"acao": "compose_up", "arquivo": str(arq)})
    assert cmds.lista[-1] == ["docker", "compose", "-f", str(arq), "up", "-d", "--remove-orphans"]
    assert p.acao_docker({"acao": "compose_down", "arquivo": str(arq)}) == "OK"
    assert cmds.lista[-1] == ["docker", "compose", "-f", str(arq), "down"]
    with pytest.raises(p.Erro, match="não encontrado"):
        p.acao_docker({"acao": "compose_up", "arquivo": "~/nada.yml"})


def test_docker_acao_desconhecida(p):
    with pytest.raises(p.Erro, match="desconhecida"):
        p.acao_docker({"acao": "explodir"})


def test_info_docker_junta_tudo_e_reaproveita_o_uso(p, cmds, monkeypatch):
    import json as _json
    monkeypatch.setattr(p, "docker_ligado", lambda: True)
    monkeypatch.setitem(p._USO, "quando", 0.0)
    monkeypatch.setitem(p._USO, "dados", {})
    a, b = "a" * 64, "b" * 64
    cmds.responder(lambda c: c[:3] == ["docker", "ps", "-a"], 0, "\n".join(_json.dumps(x) for x in [
        {"ID": a, "Names": "web", "Image": "nginx", "State": "running", "Status": "Up", "Ports": "0.0.0.0:8081->80/tcp"},
        {"ID": b, "Names": "job", "Image": "alpine", "State": "exited", "Status": "Exited (0)"}]))
    cmds.responder(lambda c: c[:2] == ["docker", "inspect"], 0,
                   f'"{a}"\t268435456\t{{"com.docker.compose.project": "site", "criado-por": "jenkins"}}\n"{b}"\t0\tnull')
    cmds.responder(lambda c: c[:2] == ["docker", "stats"], 0, _json.dumps({"ID": a, "CPUPerc": "1.5%", "MemUsage": "10MiB / 256MiB"}))
    cmds.responder(lambda c: c[:2] == ["docker", "images"], 0, '{"ID": "i1", "Repository": "nginx", "Tag": "alpine", "Size": "63MB"}')
    cmds.responder(lambda c: c[:3] == ["docker", "volume", "ls"], 0, '{"Name": "dados", "Driver": "local"}')
    cmds.responder(lambda c: c[:3] == ["docker", "network", "ls"], 0, '{"Name": "bridge", "Driver": "bridge"}\n{"Name": "rede", "Driver": "bridge"}')
    cmds.responder(lambda c: c[:3] == ["docker", "compose", "ls"], 0, '[{"Name": "site", "Status": "running(1)", "ConfigFiles": "/x/compose.yml"}]')
    d = p.info_docker()
    web, job = d["containers"]
    assert web == {"id": a[:12], "nome": "web", "imagem": "nginx", "estado": "running", "status": "Up", "portas": "0.0.0.0:8081->80/tcp",
                   "criado": "", "limite_memoria": 268435456, "projeto": "site", "origem": "jenkins", "cpu": "1.5%", "uso_memoria": "10MiB / 256MiB"}
    assert job["limite_memoria"] == 0 and job["projeto"] == "" and job["cpu"] == ""
    assert d["imagens"] == [{"id": "i1", "nome": "nginx:alpine", "tamanho": "63MB", "criada": ""}]
    assert d["volumes"] == [{"nome": "dados", "driver": "local"}]
    assert [r["padrao"] for r in d["redes"]] == [True, False]
    assert d["projetos"] == [{"nome": "site", "status": "running(1)", "arquivos": "/x/compose.yml"}]
    p.info_docker()  # logo depois: usa a medição guardada, sem rodar "docker stats" de novo
    assert sum(1 for c in cmds.lista if c[:2] == ["docker", "stats"]) == 1


def test_info_docker_desligado(p, cmds, monkeypatch):
    monkeypatch.setattr(p, "docker_ligado", lambda: False)
    monkeypatch.setattr(p, "servico_ativo", lambda n: "inactive")
    assert p.info_docker() == {"ligado": False, "servico": "inactive"}
