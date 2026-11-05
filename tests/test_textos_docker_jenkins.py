"""Textos exatos que o aluno vê na aba Docker e Jenkins (escritos a partir do teste de mutantes)."""
import pytest


def erro(p, fn, d):
    with pytest.raises(p.Erro) as e:
        fn(d)
    return str(e.value)


@pytest.mark.parametrize("d,texto", [
    ({"acao": "start", "container": ""}, "Container inválido."),
    ({"acao": "logs", "container": ""}, "Container inválido."),
    ({"acao": "terminal", "container": ""}, "Container inválido."),
    ({"acao": "inspecionar", "container": ""}, "Container inválido."),
    ({"acao": "sugestao", "imagem": ""}, "Imagem inválida."),
    ({"acao": "volume_criar", "nome": ""}, "Nome de volume inválido."),
    ({"acao": "volume_rm", "nome": ""}, "Volume inválido."),
    ({"acao": "rede_criar", "nome": ""}, "Nome de rede inválido."),
    ({"acao": "rede_rm", "nome": ""}, "Rede inválida."),
    ({"acao": "exec", "container": "web"}, "Informe o container e o comando."),
    ({"acao": "rmi", "imagem": ""}, "Imagem inválida."),
    ({"acao": "pull", "imagem": ""}, "Nome de imagem inválido (ex.: nginx:alpine)."),
    ({"acao": "run"}, "Informe a imagem (ex.: nginx:alpine)."),
    ({"acao": "run", "imagem": "a", "volumes": "x"}, "Volume inválido: x (use nome-do-volume:/caminho ou ~/pasta:/caminho)"),
    ({"acao": "run", "imagem": "a", "nome": "a b"}, "Nome inválido: use letras, números, - _ ."),
    ({"acao": "run", "imagem": "a", "portas": "1"}, "Porta inválida: 1 (use PC:CONTAINER, ex.: 8081:80; portas vão de 1 a 65535)"),
    ({"acao": "run", "imagem": "a", "memoria": "x"}, "Memória inválida (ex.: 512m ou 1g)."),
    ({"acao": "run", "imagem": "a", "env": "X"}, "Variável inválida: X (use NOME=valor)"),
    ({"acao": "run", "imagem": "a", "cpus": "x"}, "CPUs inválido (ex.: 0.5 ou 1)."),
    ({"acao": "run", "imagem": "a", "rede": "a b"}, "Rede inválida."),
    ({"acao": "run", "imagem": "a", "comando": "'"}, "O comando tem aspas abertas e não fechadas. Confira as aspas do comando."),
    ({"acao": "compose_up", "arquivo": "~/x.yml"}, "Arquivo compose não encontrado."),
    ({"acao": "compose_salvar", "arquivo": "~/x.yml"}, "O arquivo precisa se chamar docker-compose.yml ou compose.yaml."),
    ({"acao": "nada"}, "Ação de Docker desconhecida."),
])
def test_erros_docker_exatos(p, cmds, d, texto):
    assert erro(p, p.acao_docker, d) == texto


@pytest.mark.parametrize("d,texto,cmd", [
    ({"acao": "volume_criar", "nome": "v"}, "Volume 'v' criado.", ["docker", "volume", "create", "v"]),
    ({"acao": "volume_rm", "nome": "v"}, "Volume 'v' apagado.", ["docker", "volume", "rm", "v"]),
    ({"acao": "rede_criar", "nome": "r"}, "Rede 'r' criada. Containers na mesma rede se encontram pelo nome.", ["docker", "network", "create", "r"]),
    ({"acao": "rede_rm", "nome": "r"}, "Rede 'r' apagada.", ["docker", "network", "rm", "r"]),
    ({"acao": "rmi", "imagem": "a"}, "Imagem apagada.", ["docker", "rmi", "a"]),
    ({"acao": "terminal", "container": "web"}, "Abrindo um terminal dentro do container.", None),
    ({"acao": "limpar"}, "", ["docker", "system", "prune", "-f"]),
])
def test_respostas_docker_exatas(p, cmds, monkeypatch, d, texto, cmd):
    abertos = []
    monkeypatch.setattr(p, "lancar", lambda c, cwd=None: abertos.append(c))
    assert p.acao_docker(d) == texto
    if cmd:
        assert cmds.lista[-1] == cmd
    else:
        assert abertos == [["xfce4-terminal", "--title=Terminal do container web", "-x", "docker", "exec", "-it", "web",
                            "sh", "-c", "command -v bash >/dev/null && exec bash || exec sh"]]


def test_respostas_longas_cortadas(p, cmds):
    cmds.responder(lambda c: c[:3] == ["docker", "system", "prune"], 0, "x" * 2000 + "FIM")
    assert p.acao_docker({"acao": "limpar"}) == ("x" * 2000 + "FIM")[-1500:]
    cmds.responder(lambda c: c[:2] == ["docker", "pull"], 0, "y" * 3000 + "OK")
    assert p.acao_docker({"acao": "pull", "imagem": "a"}) == ("y" * 3000 + "OK")[-2000:]
    cmds.responder(lambda c: c[:2] == ["docker", "logs"], 0, "linha")
    assert p.acao_docker({"acao": "logs", "container": "web"}) == "linha"
    cmds.responder(lambda c: c[:2] == ["docker", "inspect"], 0, "[{}]")
    assert p.acao_docker({"acao": "inspecionar", "container": "web"}) == "[{}]"
    assert cmds.lista[-1] == ["docker", "inspect", "web"]


def test_run_textos_exatos(p, cmds):
    cid = "c" * 64
    cmds.responder(lambda c: c[:2] == ["docker", "run"], 0, cid)
    cmds.responder(lambda c: c[:2] == ["docker", "inspect"], 0, "running 0")
    assert p.acao_docker({"acao": "run", "imagem": "alpine", "nome": "al"}) == (
        "Container al criado e rodando.\nA imagem alpine não tem um programa que fique rodando sozinho, então usei o comando "
        "sleep infinity para o container continuar ligado. Use o Terminal dele para trabalhar.")
    cmds.respostas.clear()
    cmds.responder(lambda c: c[:2] == ["docker", "run"], 0, cid)
    cmds.responder(lambda c: c[:2] == ["docker", "inspect"], 0, "exited 0")
    cmds.responder(lambda c: c[:2] == ["docker", "logs"], 0, "pronto")
    assert p.acao_docker({"acao": "run", "imagem": "meu-script", "nome": "s"}) == (
        "O container s rodou o programa dele e terminou com sucesso (programas de uma vez só, como scripts, param quando "
        "acabam; servidores continuam ligados). Saída:\npronto")
    assert cmds.lista[-1] == ["docker", "logs", "--tail", "15", cid[:12]]
    cmds.respostas.clear()
    cmds.responder(lambda c: c[:2] == ["docker", "run"], 0, cid)
    cmds.responder(lambda c: c[:2] == ["docker", "inspect"], 0, "exited 1")
    cmds.responder(lambda c: c[:2] == ["docker", "logs"], 0, "falhou")
    assert erro(p, p.acao_docker, {"acao": "run", "imagem": "meu-script"}) == (
        f"O container {cid[:12]} parou com erro (código 1) logo depois de ligar. Veja a saída:\nfalhou")
    cmds.respostas.clear()
    cmds.responder(lambda c: c[:2] == ["docker", "run"], 0, cid)
    cmds.responder(lambda c: c[:2] == ["docker", "inspect"], 0, "exited")
    assert "(código ?)" in erro(p, p.acao_docker, {"acao": "run", "imagem": "meu-script"})


def test_run_timeouts(p, monkeypatch):
    vistos = []
    monkeypatch.setattr(p, "rodar", lambda cmd, cwd=None, timeout=120, entrada=None, so_saida=False: vistos.append((cmd[:2], timeout)) or (0, "running 0"))
    monkeypatch.setattr(p.time, "sleep", lambda s: None)
    p.acao_docker({"acao": "run", "imagem": "nginx"})
    assert (["docker", "run"], 900) in vistos
    p.acao_docker({"acao": "pull", "imagem": "nginx"})
    assert vistos[-1] == (["docker", "pull"], 900)


def test_compose_salvar_texto_e_copia(p, cmds, home):
    arq = home / "projetos" / "app" / "compose.yaml"
    assert p.acao_docker({"acao": "compose_salvar", "arquivo": str(arq), "conteudo": "a: 1\n"}) == (
        f"Salvo em {arq} (cópia anterior em compose.yaml.bak).")
    p.acao_docker({"acao": "compose_salvar", "arquivo": str(arq), "conteudo": "a: 2\n"})
    assert (arq.parent / "compose.yaml.bak").read_text() == "a: 1\n" and arq.read_text() == "a: 2\n"
    assert ["docker", "compose", "-f", str(arq.parent / ".compose.yaml.painel"), "config", "-q"] in cmds.lista


# ---------------------------------------------------------------- Jenkins
@pytest.fixture
def jk(p, monkeypatch):
    pedidos, respostas = [], {}

    def req(caminho, dados=None, tipo=None, timeout=20):
        pedidos.append((caminho, dados, tipo, timeout))
        for trecho, txt in respostas.items():
            if trecho in caminho:
                return 200, txt
        return 200, ""

    monkeypatch.setattr(p.JEN, "req", req)
    monkeypatch.setattr(p.time, "sleep", lambda s: None)
    return pedidos, respostas


@pytest.mark.parametrize("d,texto", [
    ({"acao": "criar", "job": "p", "tipo": "pipeline"}, "Pipeline 'p' criado."),
    ({"acao": "criar", "job": "s", "tipo": "pipeline_scm", "repo": "https://github.com/a/b.git"}, "Pipeline do Git 's' criado."),
    ({"acao": "criar", "job": "f", "tipo": "freestyle"}, "Freestyle 'f' criado."),
    ({"acao": "criar", "job": "d", "tipo": "pasta"}, "Pasta 'd' criado."),
    ({"acao": "criar", "job": "m", "tipo": "multibranch", "repo": "https://github.com/a/b.git"},
     "Multibranch 'm' criado. O Jenkins está procurando as branches com Jenkinsfile."),
    ({"acao": "construir", "job": "a", "parametros": {"X": "1"}}, "Construção de 'a' iniciada com os valores escolhidos."),
    ({"acao": "construir", "job": "a", "parametros": {}}, "Construção de 'a' iniciada."),
    ({"acao": "desativar", "job": "a"}, "Job desativado (não roda até ser ativado)."),
    ({"acao": "apagar_credencial", "id": "c"}, "Credencial 'c' apagada."),
])
def test_respostas_jenkins_exatas(p, jk, d, texto):
    assert p.acao_jenkins(d) == texto


def test_pedidos_jenkins_exatos(p, jk):
    pedidos, _ = jk
    p.acao_jenkins({"acao": "desativar", "job": "pasta/a"})
    assert pedidos[-1][:3] == ("/job/pasta/job/a/disable", b"", None)
    p.acao_jenkins({"acao": "apagar_credencial", "id": "minha.cred"})
    assert pedidos[-1][:2] == ("/credentials/store/system/domain/_/credential/minha.cred/doDelete", b"")
    p.acao_jenkins({"acao": "console", "job": "a"})
    assert pedidos[-1][0] == "/job/a/lastBuild/consoleText" and pedidos[-1][3] == 30


@pytest.mark.parametrize("d,texto", [
    ({"acao": "criar", "job": ""}, "Nome inválido: use letras, números, - _ . (sem espaços)"),
    ({"acao": "apagar_credencial", "id": "a b"}, "Credencial inválida."),
    ({"acao": "copiar", "job": "a"}, "Nome da cópia inválido."),
    ({"acao": "console", "job": "a", "numero": "x"}, "Número de build inválido."),
    ({"acao": "x", "job": "a"}, "Ação de Jenkins desconhecida."),
    ({"acao": "construir", "job": ""}, "Job inválido."),
])
def test_erros_jenkins_exatos(p, jk, d, texto):
    assert erro(p, p.acao_jenkins, d) == texto


def test_console_corta_e_so_da_dica_em_falha(p, jk):
    _, resp = jk
    resp["consoleText"] = "z" * 40000 + "\nscript returned exit code 127\nFinished: UNSTABLE\n"
    r = p.acao_jenkins({"acao": "console", "job": "a"})
    assert r.startswith("z") and len(r) == 30000 + len("\nDica: Algum comando do script não existe na máquina. Confira a digitação ou instale o programa.")
    resp["consoleText"] = "script returned exit code 127\nFinished: SUCCESS\n"
    assert "Dica" not in p.acao_jenkins({"acao": "console", "job": "a"})


def test_ver_config_sem_script_e_sem_gatilho(p, jk):
    _, resp = jk
    resp["config.xml"] = p.xml_item("pasta", {}).decode()
    assert p.acao_jenkins({"acao": "ver_config", "job": "d"}) == {"campo": None, "valor": "", "cron": "", "cron_scm": "",
                                                                  "repo": "", "gatilhos_ok": False}
    resp["config.xml"] = p.xml_item("pipeline_scm", {"repo": "https://github.com/a/b.git", "cron_scm": "H/5 * * * *"}).decode()
    v = p.acao_jenkins({"acao": "ver_config", "job": "s"})
    assert v == {"campo": None, "valor": "", "cron": "", "cron_scm": "H/5 * * * *", "repo": "https://github.com/a/b.git", "gatilhos_ok": True}
