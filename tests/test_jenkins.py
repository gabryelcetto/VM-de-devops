"""Jenkins: XML dos itens e das credenciais (sem Jenkins de verdade)."""
import xml.etree.ElementTree as ET

import pytest


def xml(p, tipo, **d):
    return ET.fromstring(p.xml_item(tipo, d).split(b"\n", 1)[1])


def test_pipeline_com_script_e_gatilhos(p):
    r = xml(p, "pipeline", script="pipeline { agent any }\n// < & ]]>", cron="H 8 * * 1-5", cron_scm="H/5 * * * *")
    assert r.tag == "flow-definition"
    assert r.find("definition/script").text == "pipeline { agent any }\n// < & ]]>"  # caracteres especiais preservados
    specs = [e.text for e in r.iter("spec")]
    assert specs == ["H/5 * * * *", "H 8 * * 1-5"]
    assert r.find("definition/sandbox").text == "true"


def test_pipeline_padrao(p):
    r = xml(p, "pipeline")
    assert "Ola do Jenkins" in r.find("definition/script").text
    assert r.find("description").text == "Criado pelo Painel DevOps"
    assert r.find("properties").find("*") is None  # sem gatilho, nenhuma propriedade


def test_pipeline_do_git(p):
    r = xml(p, "pipeline_scm", repo="https://github.com/gabryel/app.git", branch="dev", jenkinsfile="ci/Jenkinsfile", credencial="github")
    assert r.find(".//url").text == "https://github.com/gabryel/app.git"
    assert r.find(".//credentialsId").text == "github"
    assert r.find(".//hudson.plugins.git.BranchSpec/name").text == "*/dev"
    assert r.find("definition/scriptPath").text == "ci/Jenkinsfile"
    r2 = xml(p, "pipeline_scm", repo="https://github.com/gabryel/app.git")
    assert r2.find(".//hudson.plugins.git.BranchSpec/name").text == "*/main" and r2.find(".//credentialsId") is None


def test_freestyle(p):
    r = xml(p, "freestyle", comandos="echo ok", cron="@daily")
    assert r.find("scm").get("class") == "hudson.scm.NullSCM"
    assert r.find("builders/hudson.tasks.Shell/command").text == "echo ok"
    assert r.find("triggers/hudson.triggers.TimerTrigger/spec").text == "@daily"
    r2 = xml(p, "freestyle", repo="https://github.com/gabryel/app.git")
    assert r2.find("scm").get("class") == "hudson.plugins.git.GitSCM"


def test_multibranch_e_pasta(p):
    r = xml(p, "multibranch", repo="git@github.com:gabryel/app.git", credencial="ssh-key")
    assert r.find(".//remote").text == "git@github.com:gabryel/app.git"
    assert r.find(".//source/credentialsId").text == "ssh-key"
    assert r.find("factory/scriptPath").text == "Jenkinsfile"
    assert xml(p, "pasta", descricao="minha pasta").find("description").text == "minha pasta"


@pytest.mark.parametrize("tipo,d,msg", [
    ("pipeline", {"credencial": "a b"}, "Credencial inválida"),
    ("pipeline", {"cron": "$(id)"}, "Horário inválido"),
    ("pipeline_scm", {"repo": ""}, "URL do repositório inválida"),
    ("multibranch", {"repo": "https://github.com/usuario/repositorio.git"}, "Troque o endereço"),
    ("orquestra", {}, "Tipo de item desconhecido"),
])
def test_item_recusado(p, tipo, d, msg):
    with pytest.raises(p.Erro, match=msg):
        p.xml_item(tipo, d)


@pytest.fixture
def jenkins_falso(p, monkeypatch):
    enviados = []

    def req(caminho, dados=None, tipo=None, timeout=20):
        if caminho.endswith("/api/json?tree=credentials[id,displayName,typeName,description]"):
            return 200, '{"credentials": [{"id": "ja-existe", "displayName": "x", "typeName": "y"}]}'
        enviados.append((caminho, dados))
        return 200, ""

    monkeypatch.setattr(p.JEN, "req", req)
    return enviados


def test_credencial_token(p, jenkins_falso):
    assert "criada" in p.criar_credencial({"tipo": "usuario", "id": "github", "usuario": "gabryel", "senha": "ghp_abc"})
    caminho, corpo = jenkins_falso[-1]
    assert caminho.endswith("/createCredentials")
    r = ET.fromstring(corpo)
    assert r.find("password").text == "ghp_abc" and r.find("username").text == "gabryel" and r.find("id").text == "github"


@pytest.mark.parametrize("d,msg", [
    ({"tipo": "usuario", "id": "x", "usuario": "", "senha": "ghp_a"}, "Preencha"),
    ({"tipo": "usuario", "id": "x", "usuario": "a", "senha": "minhasenha"}, "token do GitHub"),
    ({"tipo": "usuario", "id": "a b", "usuario": "a", "senha": "ghp_a"}, "ID inválido"),
    ({"tipo": "segredo", "id": "x", "segredo": " "}, "Preencha o segredo"),
    ({"tipo": "ssh", "id": "x", "chave": "ssh-ed25519 AAAA publica"}, "chave PRIVADA"),
    ({"tipo": "ssh", "id": "x", "usar_minha_chave": True}, "ainda não tem chave"),
    ({"tipo": "certificado", "id": "x"}, "desconhecido"),
    ({"tipo": "segredo", "id": "ja-existe", "segredo": "s"}, "Já existe uma credencial"),
])
def test_credencial_recusada(p, jenkins_falso, d, msg):
    with pytest.raises(p.Erro, match=msg):
        p.criar_credencial(d)
    assert jenkins_falso == []


@pytest.mark.parametrize("prefixo", ["ghp_", "github_pat_", "gho_", "ghs_"])
def test_credencial_prefixos_de_token(p, jenkins_falso, prefixo):
    p.criar_credencial({"tipo": "usuario", "id": "t", "usuario": "a", "senha": prefixo + "x"})
    assert len(jenkins_falso) == 1


def test_credencial_ssh_da_minha_chave(p, home, jenkins_falso):
    (home / ".ssh").mkdir()
    (home / ".ssh" / "id_ed25519").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----\n")
    p.criar_credencial({"tipo": "ssh", "id": "minha", "usar_minha_chave": True})
    r = ET.fromstring(jenkins_falso[-1][1])
    assert "abc" in r.find(".//privateKey").text and r.find("username").text == "git"


class JenkinsFalso:
    """Faz o papel do Jenkins: guarda os pedidos e devolve respostas por trecho do caminho."""

    def __init__(self, p):
        self.p, self.pedidos, self.respostas, self.falhas = p, [], {}, []

    def __call__(self, caminho, dados=None, tipo=None, timeout=20):
        self.pedidos.append((caminho, dados, tipo))
        for trecho, erro in list(self.falhas):
            if trecho in caminho:
                self.falhas.remove((trecho, erro))
                raise erro
        for trecho, txt in self.respostas.items():
            if trecho in caminho:
                return 200, txt
        return 200, ""


@pytest.fixture
def jk(p, monkeypatch):
    j = JenkinsFalso(p)
    monkeypatch.setattr(p.JEN, "req", j)
    monkeypatch.setattr(p.time, "sleep", lambda s: None)
    return j


def test_criar_pipeline(p, jk):
    assert p.acao_jenkins({"acao": "criar", "job": "app"}) == "Pipeline 'app' criado."
    caminho, dados, tipo = jk.pedidos[-1]
    assert caminho == "/createItem?name=app" and tipo == "application/xml" and b"flow-definition" in dados


def test_criar_dentro_de_pasta_e_multibranch(p, jk):
    assert p.acao_jenkins({"acao": "criar", "tipo": "freestyle", "job": "f", "pasta": "minha pasta"}) == "Freestyle 'minha pasta/f' criado."
    assert jk.pedidos[-1][0] == "/job/minha%20pasta/createItem?name=f"
    r = p.acao_jenkins({"acao": "criar", "tipo": "multibranch", "job": "mb", "repo": "https://github.com/a/b.git"})
    assert r.startswith("Multibranch 'mb' criado") and jk.pedidos[-1][0] == "/job/mb/build?delay=0sec"


def test_criar_nome_invalido(p, jk):
    with pytest.raises(p.Erro, match="Nome inválido"):
        p.acao_jenkins({"acao": "criar", "job": "meu job"})
    assert jk.pedidos == []


def test_criar_com_erro_500_tenta_de_novo_se_nao_criou(p, jk):
    jk.falhas.append(("createItem", p.ErroJenkins(500, "erro interno")))
    jk.falhas.append(("/job/app/api/json", p.Erro("não existe")))
    assert p.acao_jenkins({"acao": "criar", "job": "app"}) == "Pipeline 'app' criado."
    assert [c for c, _, _ in jk.pedidos].count("/createItem?name=app") == 2


def test_criar_com_erro_500_mas_criou(p, jk):
    jk.falhas.append(("createItem", p.ErroJenkins(500, "erro interno")))
    p.acao_jenkins({"acao": "criar", "job": "app"})
    assert [c for c, _, _ in jk.pedidos].count("/createItem?name=app") == 1


def test_criar_com_erro_400_repassa(p, jk):
    jk.falhas.append(("createItem", p.ErroJenkins(400, "Já existe um item")))
    with pytest.raises(p.Erro, match="Já existe"):
        p.acao_jenkins({"acao": "criar", "job": "app"})


def test_construir(p, jk):
    assert p.acao_jenkins({"acao": "construir", "job": "app"}) == "Construção de 'app' iniciada."
    assert jk.pedidos[-1][0] == "/job/app/build?delay=0sec"
    p.acao_jenkins({"acao": "construir", "job": "app", "parametros": {"NOME": "a b", "N": 1}})
    caminho, dados, tipo = jk.pedidos[-1]
    assert caminho == "/job/app/buildWithParameters?delay=0sec" and dados == b"NOME=a+b&N=1" and tipo == "application/x-www-form-urlencoded"
    jk.falhas.append(("/build?", p.ErroJenkins(400, "precisa de parâmetros")))
    p.acao_jenkins({"acao": "construir", "job": "app"})
    assert jk.pedidos[-1][0] == "/job/app/buildWithParameters?delay=0sec"
    jk.falhas.append(("/build?", p.ErroJenkins(404, "não existe")))
    with pytest.raises(p.Erro, match="não existe"):
        p.acao_jenkins({"acao": "construir", "job": "app"})


def test_parametros(p, jk):
    jk.respostas["parameterDefinitions"] = ('{"property": [{}, {"parameterDefinitions": [{"name": "AMBIENTE", "type": "ChoiceParameterDefinition",'
                                            ' "choices": ["dev", "prod"], "defaultParameterValue": {"value": "dev"}}]}]}')
    r = p.acao_jenkins({"acao": "parametros", "job": "app"})
    assert r == {"parametros": [{"nome": "AMBIENTE", "tipo": "Choice", "descricao": "", "opcoes": ["dev", "prod"], "padrao": "dev"}]}


def test_console_com_dica(p, jk):
    jk.respostas["consoleText"] = "+ app\nsh: app: not found\nscript returned exit code 127\nFinished: FAILURE\n"
    r = p.acao_jenkins({"acao": "console", "job": "app"})
    assert "Dica: Algum comando do script não existe" in r
    jk.respostas["consoleText"] = "ok\nFinished: SUCCESS\n"
    assert "Dica" not in p.acao_jenkins({"acao": "console", "job": "app", "numero": 3})
    assert jk.pedidos[-1][0] == "/job/app/3/consoleText"
    with pytest.raises(p.Erro, match="Número de build"):
        p.acao_jenkins({"acao": "console", "job": "app", "numero": "3; x"})


def test_copiar_usa_config_do_original(p, jk):
    jk.respostas["config.xml"] = "<project>original</project>"
    assert "pronta para construir" in p.acao_jenkins({"acao": "copiar", "job": "pasta/app", "novo": "app-2"})
    caminho, dados, _ = jk.pedidos[-1]
    assert caminho == "/job/pasta/createItem?name=app-2" and dados == b"<project>original</project>"
    with pytest.raises(p.Erro, match="Nome da cópia"):
        p.acao_jenkins({"acao": "copiar", "job": "app", "novo": "a b"})


def test_ver_e_salvar_config_pipeline(p, jk):
    jk.respostas["config.xml"] = p.xml_item("pipeline", {"script": "echo 1", "cron": "H 8 * * *"}).decode()
    v = p.acao_jenkins({"acao": "ver_config", "job": "app"})
    assert v["campo"] == "script" and v["valor"] == "echo 1" and v["cron"] == "H 8 * * *" and v["gatilhos_ok"]
    p.acao_jenkins({"acao": "salvar_config", "job": "app", "valor": "echo 2", "cron": "", "cron_scm": "H/5 * * * *"})
    salvo = ET.fromstring(jk.pedidos[-1][1].split(b"\n", 1)[1])
    assert salvo.find("definition/script").text == "echo 2"
    assert [e.text for e in salvo.iter("spec")] == ["H/5 * * * *"]


def test_salvar_config_freestyle_mantem_ordem(p, jk):
    jk.respostas["config.xml"] = p.xml_item("freestyle", {"comandos": "echo a", "cron": "@daily"}).decode()
    v = p.acao_jenkins({"acao": "ver_config", "job": "f"})
    assert v["campo"] == "comandos" and v["cron"] == "@daily"
    p.acao_jenkins({"acao": "salvar_config", "job": "f", "cron": "", "cron_scm": ""})
    salvo = ET.fromstring(jk.pedidos[-1][1].split(b"\n", 1)[1])
    tags = [e.tag for e in salvo]
    assert tags.index("triggers") < tags.index("builders") and salvo.find("triggers").find("*") is None


def test_salvar_config_sem_script(p, jk):
    jk.respostas["config.xml"] = p.xml_item("pasta", {}).decode()
    with pytest.raises(p.Erro, match="não tem script"):
        p.acao_jenkins({"acao": "salvar_config", "job": "pasta", "valor": "x"})


@pytest.mark.parametrize("acao,caminho,msg", [
    ("parar", "/job/app/lastBuild/stop", "Pedido de parada enviado."), ("ativar", "/job/app/enable", "Job ativado."),
    ("apagar", "/job/app/doDelete", "'app' apagado."),
])
def test_acoes_simples(p, jk, acao, caminho, msg):
    assert p.acao_jenkins({"acao": acao, "job": "app"}) == msg
    assert jk.pedidos[-1][:2] == (caminho, b"")


def test_etapas(p, jk):
    jk.respostas["wfapi"] = '{"id": "4", "status": "SUCCESS", "stages": [{"name": "Build", "status": "SUCCESS", "durationMillis": 10}]}'
    assert p.acao_jenkins({"acao": "etapas", "job": "app"}) == {"numero": "4", "status": "SUCCESS",
                                                                "etapas": [{"nome": "Build", "status": "SUCCESS", "duracao": 10}]}
    jk.falhas.append(("wfapi", p.Erro("sem")))
    assert p.acao_jenkins({"acao": "etapas", "job": "app"}) == {"etapas": []}


def test_jenkins_job_invalido_e_acao_desconhecida(p, jk):
    with pytest.raises(p.Erro, match="Job inválido"):
        p.acao_jenkins({"acao": "construir", "job": "../x"})
    with pytest.raises(p.Erro, match="desconhecida"):
        p.acao_jenkins({"acao": "explodir", "job": "app"})
