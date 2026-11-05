"""Tabela completa de /api/executar: para cada pedido, a tarefa exata (ferramenta, título,
comando e pasta). Escrita a partir do teste de mutantes."""
import pytest


@pytest.fixture
def ambiente(p, home, tmp_path, monkeypatch):
    for nome in ("tf", "py", "img", "site", "repo"):
        (home / "projetos" / nome).mkdir()
    (home / "projetos/tf/main.tf").write_text("")
    (home / "projetos/py/app.py").write_text("")
    (home / "projetos/py/.venv/bin").mkdir(parents=True)
    (home / "projetos/py/.venv/bin/python").write_text("")
    (home / "projetos/img/Dockerfile").write_text("FROM alpine\n")
    (home / "projetos/site/docker-compose.yaml").write_text("services: {}\n")
    (home / "projetos/repo/.git").mkdir()
    mon = tmp_path / "mon" / "docker-compose.yml"
    mon.parent.mkdir()
    mon.write_text("services: {}\n")
    monkeypatch.setattr(p, "MON_COMPOSE", mon)
    return home, mon


def casos(h, mon):
    P = str(h / "projetos")
    py = f"{P}/py/.venv/bin/python"
    tf = ["-input=false", "-no-color"]
    return [
        ({"ferramenta": "docker", "acao": "pull", "imagem": " nginx:alpine "},
         ("docker", "docker pull nginx:alpine", ["docker", "pull", "nginx:alpine"], None)),
        ({"ferramenta": "docker", "acao": "compose_up", "arquivo": f"{P}/site/docker-compose.yaml"},
         ("docker", "docker compose up -d (site)", ["docker", "compose", "-f", f"{P}/site/docker-compose.yaml", "up", "-d", "--remove-orphans"], f"{P}/site")),
        ({"ferramenta": "docker", "acao": "compose_down", "arquivo": f"{P}/site/docker-compose.yaml"},
         ("docker", "docker compose down (site)", ["docker", "compose", "-f", f"{P}/site/docker-compose.yaml", "down"], f"{P}/site")),
        ({"ferramenta": "docker", "acao": "compose_logs", "arquivo": f"{P}/site/docker-compose.yaml"},
         ("docker", "docker compose logs --tail (site)", ["docker", "compose", "-f", f"{P}/site/docker-compose.yaml", "logs", "--tail", "200", "--no-color"], f"{P}/site")),
        ({"ferramenta": "docker", "acao": "compose_down_projeto", "projeto": " site-jenkins "},
         ("docker", "docker compose -p site-jenkins down", ["docker", "compose", "-p", "site-jenkins", "down"], None)),
        ({"ferramenta": "docker", "acao": "compose_logs_projeto", "projeto": "monitoramento"},
         ("docker", "docker compose -p monitoramento logs", ["docker", "compose", "-p", "monitoramento", "logs", "--tail", "200", "--no-color"], None)),
        ({"ferramenta": "docker", "acao": "build", "pasta": f"{P}/img"},
         ("docker", "docker build -t img", ["docker", "build", "-t", "img", "."], f"{P}/img")),
        ({"ferramenta": "docker", "acao": "build", "pasta": f"{P}/img", "tag": "minha:1"},
         ("docker", "docker build -t minha:1", ["docker", "build", "-t", "minha:1", "."], f"{P}/img")),
        ({"ferramenta": "git", "acao": "clonar", "url": " https://github.com/a/b.git "},
         ("git", "git clone https://github.com/a/b.git", ["git", "clone", "--progress", "https://github.com/a/b.git"], P)),
        ({"ferramenta": "git", "acao": "pull", "repo": f"{P}/repo"},
         ("git", "git pull (repo)", ["git", "pull", "--no-rebase", "--no-edit"], f"{P}/repo")),
        ({"ferramenta": "git", "acao": "push", "repo": f"{P}/repo"},
         ("git", "git push (repo)", ["git", "push", "--follow-tags", "-u", "origin", "HEAD"], f"{P}/repo")),
        ({"ferramenta": "git", "acao": "fetch", "repo": f"{P}/repo"},
         ("git", "git fetch (repo)", ["git", "fetch", "--all", "--prune"], f"{P}/repo")),
        ({"ferramenta": "vscode", "acao": "instalar", "extensao": " ms-python.python "},
         ("vscode", "instalar extensão ms-python.python", ["code", "--install-extension", "ms-python.python"], None)),
        ({"ferramenta": "vscode", "acao": "remover", "extensao": "redhat.vscode-yaml"},
         ("vscode", "remover extensão redhat.vscode-yaml", ["code", "--uninstall-extension", "redhat.vscode-yaml"], None)),
        ({"ferramenta": "monitoramento", "acao": "desligar"},
         ("monitoramento", "desligar o monitoramento", ["docker", "compose", "-f", str(mon), "down"], str(mon.parent))),
        ({"ferramenta": "monitoramento", "acao": "reiniciar"},
         ("monitoramento", "reiniciar o monitoramento", ["docker", "compose", "-f", str(mon), "restart"], str(mon.parent))),
        ({"ferramenta": "projeto", "acao": "apagar", "pasta": f"{P}/py"},
         ("projeto", "apagar projeto py", ["bash", "-c", 'echo "== apagando a pasta $PWD =="; cd .. && rm -rf -- "$1" && echo "Projeto apagado."',
                                          "apagar", f"{P}/py"], f"{P}/py")),
        ({"ferramenta": "projeto", "acao": "apagar", "pasta": f"{P}/site"},
         ("projeto", "apagar projeto site (compose down)", ["bash", "-c",
          "echo '== docker compose down: removendo containers e volumes do projeto =='; docker compose -f docker-compose.yaml down -v --remove-orphans"
          ' && echo "== apagando a pasta $PWD =="; cd .. && rm -rf -- "$1" && echo "Projeto apagado."', "apagar", f"{P}/site"], f"{P}/site")),
        ({"ferramenta": "terraform", "acao": "fmt", "pasta": f"{P}/tf"},
         ("terraform", "terraform fmt (tf)", ["terraform", "fmt", "-diff", "-no-color"], f"{P}/tf")),
        ({"ferramenta": "terraform", "acao": "output", "pasta": f"{P}/tf"},
         ("terraform", "terraform output (tf)", ["terraform", "output", "-no-color"], f"{P}/tf")),
        ({"ferramenta": "terraform", "acao": "show", "pasta": f"{P}/tf"},
         ("terraform", "terraform show (tf)", ["terraform", "show", "-no-color"], f"{P}/tf")),
        ({"ferramenta": "terraform", "acao": "graph", "pasta": f"{P}/tf"},
         ("terraform", "terraform graph (tf)", ["terraform", "graph"], f"{P}/tf")),
        ({"ferramenta": "terraform", "acao": "init", "pasta": f"{P}/tf"},
         ("terraform", "terraform init (tf)", ["terraform", "init"] + tf, f"{P}/tf")),
        ({"ferramenta": "python", "acao": "rodar", "pasta": f"{P}/py", "script": f"{P}/py/app.py"},
         ("python", "python app.py", [py, "-u", "app.py"], f"{P}/py")),
        ({"ferramenta": "python", "acao": "venv", "pasta": f"{P}/py"},
         ("python", "criar .venv (py)", ["python3", "-m", "venv", ".venv"], f"{P}/py")),
        ({"ferramenta": "python", "acao": "pip", "pasta": f"{P}/py", "pacotes": "Flask Django>=5"},
         ("python", "pip install Flask Django>=5", [py, "-m", "pip", "install", "Flask", "Django>=5"], f"{P}/py")),
        ({"ferramenta": "python", "acao": "pytest", "pasta": f"{P}/py"},
         ("python", "pytest (py)", [py, "-m", "pytest", "-v"], f"{P}/py")),
        ({"ferramenta": "python", "acao": "freeze", "pasta": f"{P}/py"},
         ("python", "pip freeze > requirements.txt (py)", ["sh", "-c", '"$1" -m pip freeze | tee requirements.txt', "freeze", py], f"{P}/py")),
        ({"ferramenta": "python", "acao": "piplist", "pasta": f"{P}/py"},
         ("python", "pip list (py)", [py, "-m", "pip", "list"], f"{P}/py")),
    ]


def test_tabela_de_tarefas(p, ambiente, tarefas):
    h, mon = ambiente
    for pedido, (ferr, titulo, cmd, cwd) in casos(h, mon):
        p.acao_executar(pedido)
        t = tarefas[-1]
        assert (t["ferramenta"], t["titulo"], t["cmd"], t["cwd"]) == (ferr, titulo, cmd, cwd), pedido


def test_tabela_de_erros(p, ambiente):
    h, _ = ambiente
    P = str(h / "projetos")
    for pedido, texto in [
        ({"ferramenta": "docker", "acao": "pull", "imagem": "a b"}, "Nome de imagem inválido (ex.: nginx:alpine)."),
        ({"ferramenta": "docker", "acao": "compose_up", "arquivo": "~/nada.yml"}, "Arquivo compose não encontrado."),
        ({"ferramenta": "docker", "acao": "compose_down_projeto"}, "Nome de projeto Compose inválido."),
        ({"ferramenta": "docker", "acao": "build", "pasta": f"{P}/py"}, "Pasta sem Dockerfile ou nome de imagem inválido."),
        ({"ferramenta": "git", "acao": "clonar"}, "URL inválida (ex.: https://github.com/usuario/repositorio.git)."),
        ({"ferramenta": "git", "acao": "pull", "repo": f"{P}/py"}, "Isto não é um repositório Git."),
        ({"ferramenta": "vscode", "acao": "instalar"}, "ID de extensão inválido (ex.: ms-python.python)."),
        ({"ferramenta": "vscode", "acao": "x", "extensao": "a.b"}, "Ação do VS Code desconhecida."),
        ({"ferramenta": "monitoramento", "acao": "x"}, "Ação de monitoramento desconhecida."),
        ({"ferramenta": "projeto", "acao": "apagar"}, "Só dá para apagar pastas de projeto que ficam direto em ~/projetos."),
        ({"ferramenta": "projeto", "acao": "renomear", "pasta": f"{P}/py"}, "Ação desconhecida."),
        ({"ferramenta": "outra", "acao": "apagar"}, "Ação desconhecida."),
        ({"ferramenta": "terraform", "acao": "plan", "pasta": f"{P}/py"}, "Esta pasta não tem arquivos .tf."),
        ({"ferramenta": "terraform", "acao": "x", "pasta": f"{P}/tf"}, "Ação do Terraform desconhecida."),
        ({"ferramenta": "python", "acao": "rodar", "pasta": f"{P}/py"}, "Escolha um arquivo .py."),
        ({"ferramenta": "python", "acao": "pip", "pasta": f"{P}/py", "pacotes": "a;b"}, "Pacote inválido: a;b"),
        ({"ferramenta": "python", "acao": "freeze", "pasta": f"{P}/tf"}, "Crie o ambiente (.venv) primeiro."),
        ({"ferramenta": "python", "acao": "x", "pasta": f"{P}/py"}, "Ação desconhecida."),
    ]:
        with pytest.raises(p.Erro) as e:
            p.acao_executar(pedido)
        assert str(e.value) == texto, pedido


def test_monitoramento_nao_instalado_texto(p, tmp_path, monkeypatch):
    monkeypatch.setattr(p, "MON_COMPOSE", tmp_path / "nao-existe.yml")
    with pytest.raises(p.Erro) as e:
        p.acao_executar({"ferramenta": "monitoramento", "acao": "ligar"})
    assert str(e.value) == "O monitoramento não está instalado nesta VM."


def test_apagar_terraform_le_estado_com_bytes_estranhos(p, home, tarefas):
    pasta = home / "projetos" / "tf2"
    pasta.mkdir()
    (pasta / "main.tf").write_text("")
    (pasta / "terraform.tfstate").write_bytes(b'\xff{"resources": [{"mode": "managed"}]}')
    p.acao_executar({"ferramenta": "projeto", "acao": "apagar", "pasta": str(pasta)})
    assert "terraform destroy" in tarefas[-1]["cmd"][2]
