"""Tarefas com saída ao vivo (Terraform, Python, Compose, monitoramento, apagar projeto)."""
import time

import pytest


def _tf(home, nome="tf", estado=None):
    pasta = home / "projetos" / nome
    pasta.mkdir(parents=True)
    (pasta / "main.tf").write_text('resource "terraform_data" "x" {}\n')
    if estado is not None:
        (pasta / "terraform.tfstate").write_text(estado)
    return pasta


ESTADO_COM_RECURSO = '{"resources": [{"mode": "managed", "type": "docker_container", "name": "web"}]}'
ESTADO_COM_RECURSO_TF = '{\n  "resources": [\n    {\n      "mode": "managed",\n      "type": "docker_container",\n      "name": "web"\n    }\n  ]\n}'


@pytest.mark.parametrize("acao,args", [
    ("init", ["init", "-input=false", "-no-color"]), ("plan", ["plan", "-input=false", "-no-color"]),
    ("apply", ["apply", "-auto-approve", "-input=false", "-no-color"]),
    ("destroy", ["destroy", "-auto-approve", "-input=false", "-no-color"]),
    ("refresh", ["apply", "-refresh-only", "-auto-approve", "-input=false", "-no-color"]),
    ("validate", ["validate", "-no-color"]), ("state", ["state", "list"]),
])
def test_terraform(p, home, tarefas, acao, args):
    pasta = _tf(home)
    p.acao_executar({"ferramenta": "terraform", "acao": acao, "pasta": str(pasta)})
    assert tarefas[-1]["cmd"] == ["terraform"] + args and tarefas[-1]["cwd"] == str(pasta)


def test_terraform_recusas(p, home, tarefas):
    pasta = _tf(home)
    with pytest.raises(p.Erro, match="desconhecida"):
        p.acao_executar({"ferramenta": "terraform", "acao": "import", "pasta": str(pasta)})
    (home / "projetos" / "sem-tf").mkdir()
    with pytest.raises(p.Erro, match="não tem arquivos .tf"):
        p.acao_executar({"ferramenta": "terraform", "acao": "plan", "pasta": str(home / "projetos" / "sem-tf")})
    assert tarefas == []


def test_apagar_projeto_terraform_faz_destroy_antes(p, home, tarefas):
    pasta = _tf(home, estado=ESTADO_COM_RECURSO_TF)
    p.acao_executar({"ferramenta": "projeto", "acao": "apagar", "pasta": str(pasta)})
    t = tarefas[-1]
    script = t["cmd"][2]
    assert t["cmd"][:2] == ["bash", "-c"] and t["cmd"][3:] == ["apagar", str(pasta)]
    assert script.index("terraform destroy") < script.index("rm -rf")
    assert "(destroy)" in t["titulo"] and "docker compose" not in script


def test_apagar_projeto_sem_recursos_nao_faz_destroy(p, home, tarefas):
    pasta = _tf(home, estado='{"resources": []}')
    p.acao_executar({"ferramenta": "projeto", "acao": "apagar", "pasta": str(pasta)})
    assert "terraform destroy" not in tarefas[-1]["cmd"][2] and tarefas[-1]["titulo"] == "apagar projeto tf"


def test_apagar_projeto_compose(p, home, tarefas):
    pasta = home / "projetos" / "site"
    pasta.mkdir()
    (pasta / "compose.yaml").write_text("services: {}\n")
    p.acao_executar({"ferramenta": "projeto", "acao": "apagar", "pasta": str(pasta)})
    s = tarefas[-1]["cmd"][2]
    assert "docker compose -f compose.yaml down -v --remove-orphans" in s and s.index("down") < s.index("rm -rf")


def test_apagar_projeto_de_verdade(p, home):
    """Roda o script real (sem Terraform/Compose): a pasta some e nada fora dela é tocado."""
    pasta = home / "projetos" / "py"
    (pasta / "sub").mkdir(parents=True)
    (pasta / "sub" / "a.py").write_text("x")
    vizinho = home / "projetos" / "py-2"
    vizinho.mkdir()
    r = p.acao_executar({"ferramenta": "projeto", "acao": "apagar", "pasta": str(pasta)})
    for _ in range(100):
        t = p.ver_tarefa({"id": [r["tarefa"]]})
        if t["fim"]:
            break
        time.sleep(0.05)
    assert t["codigo"] == 0 and "Projeto apagado." in t["linhas"]
    assert not pasta.exists() and vizinho.exists()


@pytest.mark.parametrize("alvo", ["~", "~/projetos", "~/projetos/app/sub", "~/outra/app", "/tmp"])
def test_apagar_so_projeto_direto_em_projetos(p, home, tarefas, alvo):
    (home / "projetos" / "app" / "sub").mkdir(parents=True)
    (home / "outra" / "app").mkdir(parents=True)
    with pytest.raises(p.Erro):
        p.acao_executar({"ferramenta": "projeto", "acao": "apagar", "pasta": alvo})
    assert tarefas == []


def test_apagar_atalho_para_fora_de_projetos(p, home, tarefas):
    import os
    (home / "importante").mkdir()
    os.symlink(home / "importante", home / "projetos" / "atalho")
    with pytest.raises(p.Erro):
        p.acao_executar({"ferramenta": "projeto", "acao": "apagar", "pasta": "~/projetos/atalho"})


def test_monitoramento(p, tmp_path, monkeypatch, tarefas):
    comp = tmp_path / "docker-compose.yml"
    monkeypatch.setattr(p, "MON_COMPOSE", comp)
    with pytest.raises(p.Erro, match="não está instalado"):
        p.acao_executar({"ferramenta": "monitoramento", "acao": "ligar"})
    comp.write_text("services: {}\n")
    p.acao_executar({"ferramenta": "monitoramento", "acao": "ligar"})
    s = tarefas[-1]["cmd"][2]
    assert tarefas[-1]["cmd"][:2] == ["bash", "-c"] and tarefas[-1]["cwd"] == str(tmp_path)
    assert "zstd -d -q --long=27 -c imagens.tar.zst | docker load || exit 1" in s and s.endswith("docker compose up -d")
    p.acao_executar({"ferramenta": "monitoramento", "acao": "desligar"})
    assert tarefas[-1]["cmd"] == ["docker", "compose", "-f", str(comp), "down"]
    p.acao_executar({"ferramenta": "monitoramento", "acao": "reiniciar"})
    assert tarefas[-1]["cmd"][-1] == "restart"
    with pytest.raises(p.Erro, match="desconhecida"):
        p.acao_executar({"ferramenta": "monitoramento", "acao": "apagar"})


def test_python(p, home, tarefas):
    pasta = home / "projetos" / "py"
    pasta.mkdir()
    (pasta / "app.py").write_text("print(1)")
    p.acao_executar({"ferramenta": "python", "acao": "rodar", "pasta": str(pasta), "script": str(pasta / "app.py")})
    assert tarefas[-1]["cmd"] == ["python3", "-u", "app.py"]
    with pytest.raises(p.Erro, match="Crie o ambiente"):
        p.acao_executar({"ferramenta": "python", "acao": "pip", "pasta": str(pasta), "pacotes": "flask"})
    (pasta / ".venv" / "bin").mkdir(parents=True)
    (pasta / ".venv" / "bin" / "python").write_text("")
    py = str(pasta / ".venv" / "bin" / "python")
    p.acao_executar({"ferramenta": "python", "acao": "pip", "pasta": str(pasta), "pacotes": "flask requests==2.32"})
    assert tarefas[-1]["cmd"] == [py, "-m", "pip", "install", "flask", "requests==2.32"]
    (pasta / "requirements.txt").write_text("flask\n")
    p.acao_executar({"ferramenta": "python", "acao": "pip", "pasta": str(pasta)})
    assert tarefas[-1]["cmd"][-2:] == ["-r", "requirements.txt"]
    p.acao_executar({"ferramenta": "python", "acao": "freeze", "pasta": str(pasta)})
    assert tarefas[-1]["cmd"] == ["sh", "-c", '"$1" -m pip freeze | tee requirements.txt', "freeze", py]
    for ruim in ("flask;rm", "$(id)", "a/b"):
        with pytest.raises(p.Erro, match="Pacote inválido"):
            p.acao_executar({"ferramenta": "python", "acao": "pip", "pasta": str(pasta), "pacotes": ruim})
    with pytest.raises(p.Erro, match="arquivo .py"):
        p.acao_executar({"ferramenta": "python", "acao": "rodar", "pasta": str(pasta), "script": str(pasta / "requirements.txt")})


def test_vscode_extensao(p, tarefas):
    p.acao_executar({"ferramenta": "vscode", "acao": "instalar", "extensao": "ms-python.python"})
    assert tarefas[-1]["cmd"] == ["code", "--install-extension", "ms-python.python"]
    p.acao_executar({"ferramenta": "vscode", "acao": "remover", "extensao": "ms-python.python"})
    assert tarefas[-1]["cmd"] == ["code", "--uninstall-extension", "ms-python.python"]
    with pytest.raises(p.Erro, match="desconhecida"):
        p.acao_executar({"ferramenta": "vscode", "acao": "instalr", "extensao": "ms-python.python"})
    with pytest.raises(p.Erro, match="ID de extensão"):
        p.acao_executar({"ferramenta": "vscode", "acao": "instalar", "extensao": "--force"})


def test_docker_compose_projeto_do_jenkins(p, tarefas):
    p.acao_executar({"ferramenta": "docker", "acao": "compose_down_projeto", "projeto": "site-jenkins"})
    assert tarefas[-1]["cmd"] == ["docker", "compose", "-p", "site-jenkins", "down"]
    for ruim in ("Site", "-p", "a b", ""):
        with pytest.raises(p.Erro, match="inválido"):
            p.acao_executar({"ferramenta": "docker", "acao": "compose_logs_projeto", "projeto": ruim})


def test_git_clonar_e_pull(p, home, tarefas):
    p.acao_executar({"ferramenta": "git", "acao": "clonar", "url": "https://github.com/gabryel/app.git"})
    assert tarefas[-1]["cmd"] == ["git", "clone", "--progress", "https://github.com/gabryel/app.git"]
    with pytest.raises(p.Erro, match="URL inválida"):
        p.acao_executar({"ferramenta": "git", "acao": "clonar", "url": "--upload-pack=x"})


def test_ferramenta_desconhecida(p):
    with pytest.raises(p.Erro, match="desconhecida"):
        p.acao_executar({"ferramenta": "ansible", "acao": "rodar"})


def test_tarefa_real_com_dica_e_comando_inexistente(p, home):
    r = p.iniciar_tarefa("teste", "falha", ["sh", "-c", "echo 'port is already allocated'; exit 3"])
    for _ in range(100):
        t = p.ver_tarefa({"id": [r["tarefa"]]})
        if t["fim"]:
            break
        time.sleep(0.05)
    assert t["codigo"] == 3 and any(x.startswith("Dica: A porta já está sendo usada") for x in t["linhas"])
    assert p.ver_tarefa({"id": [r["tarefa"]], "desde": ["2"]})["linhas"] == t["linhas"][2:]
    assert p.ver_tarefa({"id": [r["tarefa"]], "desde": ["abc"]})["total"] == len(t["linhas"])
    r2 = p.iniciar_tarefa("teste", "nada", ["comando-que-nao-existe-xyz"])
    for _ in range(100):
        t2 = p.ver_tarefa({"id": [r2["tarefa"]]})
        if t2["fim"]:
            break
        time.sleep(0.05)
    assert t2["codigo"] == 127 and t2["linhas"] == ["comando não encontrado: comando-que-nao-existe-xyz"]
    with pytest.raises(p.Erro, match="não encontrada"):
        p.ver_tarefa({"id": ["nao-existe"]})
    assert any(x["id"] == r["tarefa"] for x in p.listar_tarefas()["tarefas"])


def test_parar_tarefa(p):
    r = p.iniciar_tarefa("teste", "longa", ["sleep", "30"])
    for _ in range(50):
        if r["tarefa"] in p.PROCESSOS:
            break
        time.sleep(0.02)
    assert p.parar_tarefa({"id": r["tarefa"]}) == "Tarefa interrompida."
    for _ in range(100):
        t = p.ver_tarefa({"id": [r["tarefa"]]})
        if t["fim"]:
            break
        time.sleep(0.05)
    assert t["fim"] and t["codigo"] == -15
    assert p.parar_tarefa({"id": r["tarefa"]}) == "A tarefa já terminou."
