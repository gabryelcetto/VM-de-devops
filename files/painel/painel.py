#!/usr/bin/env python3
"""Painel DevOps: mostra e altera o que o aluno criou no Docker, Jenkins, Git e VS Code.

Roda só em 127.0.0.1 (nada fica visível na rede). Toda ação que altera algo exige o
token da página (cabeçalho X-Painel-Token) e o Host precisa ser localhost: outra página
aberta no navegador não consegue mandar comandos para cá.
Só usa a biblioteca padrão do Python.
"""
import base64
import http.cookiejar
import json
import os
import re
import secrets
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORTA = int(os.environ.get("PAINEL_PORTA", "8090"))
AQUI = Path(__file__).resolve().parent
HOME = Path.home()
PROJETOS = HOME / "projetos"
TOKEN = secrets.token_urlsafe(24)
HOSTS_OK = {f"localhost:{PORTA}", f"127.0.0.1:{PORTA}"}

CONF_ARQ = HOME / ".config" / "devops-lab" / "painel.json"
CONF = {"jenkins_url": "http://localhost:8080", "jenkins_usuario": "aluno", "jenkins_senha": "devops",
        "portainer_url": "http://localhost:9000"}
try:
    CONF.update(json.loads(CONF_ARQ.read_text()))
except Exception:
    pass

NOME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}$")
REF_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:@\-]{0,254}$")
BRANCH_OK = re.compile(r"^(?!-)(?!.*\.\.)[A-Za-z0-9_./\-]{1,100}$")
PORTAS_OK = re.compile(r"^(\d{1,5}:\d{1,5}(/(tcp|udp))?)$")
MEM_OK = re.compile(r"^\d{1,6}[bkmgBKMG]?$")


class Erro(Exception):
    pass


# ---------------------------------------------------------------- utilidades
def rodar(cmd, cwd=None, timeout=120, entrada=None):
    """Executa sem shell; devolve (código, saída+erro)."""
    try:
        p = subprocess.run(cmd, cwd=cwd, input=entrada, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, f"comando não encontrado: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "tempo esgotado"


def ok_ou_erro(r):
    cod, txt = r
    if cod != 0:
        raise Erro(txt or f"falhou (código {cod})")
    return txt


def lancar(cmd, cwd=None):
    """Abre um programa gráfico sem esperar (VS Code, terminal, navegador)."""
    subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def dentro_da_home(caminho):
    p = Path(os.path.expanduser(str(caminho))).resolve()
    if p != HOME and HOME not in p.parents:
        raise Erro("Só é permitido usar pastas dentro da sua pasta pessoal.")
    return p


def arquivo_permitido(caminho):
    """Arquivos de compose podem estar na pasta pessoal ou em /opt (ex.: /opt/aula)."""
    p = Path(os.path.expanduser(str(caminho))).resolve()
    if Path("/opt") in p.parents:
        return p
    return dentro_da_home(p)


def json_linhas(txt):
    itens = []
    for linha in txt.splitlines():
        linha = linha.strip()
        if linha.startswith("{"):
            try:
                itens.append(json.loads(linha))
            except ValueError:
                pass
    return itens


def servico_ativo(nome):
    return rodar(["systemctl", "is-active", nome], timeout=10)[1].strip()


# ---------------------------------------------------------------- Docker
def docker_ligado():
    return rodar(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=30)[0] == 0


def info_docker():
    if not docker_ligado():
        return {"ligado": False, "servico": servico_ativo("docker")}
    cont = json_linhas(rodar(["docker", "ps", "-a", "--no-trunc", "--format", "{{json .}}"])[1])
    ids = [c["ID"] for c in cont]
    limites = {}
    if ids:
        cod, txt = rodar(["docker", "inspect", "--format",
                          "{{.Id}} {{.HostConfig.Memory}} {{index .Config.Labels \"com.docker.compose.project\"}}"] + ids)
        for linha in txt.splitlines():
            partes = linha.split(" ")
            if len(partes) >= 2:
                limites[partes[0]] = {"memoria": int(partes[1] or 0), "projeto": partes[2] if len(partes) > 2 else ""}
    uso = {}
    if any(c.get("State") == "running" for c in cont):
        for s in json_linhas(rodar(["docker", "stats", "--no-stream", "--no-trunc", "--format", "{{json .}}"], timeout=40)[1]):
            uso[s.get("ID", "")] = {"cpu": s.get("CPUPerc", ""), "mem": s.get("MemUsage", "")}
    containers = []
    for c in cont:
        cid = c["ID"]
        extra = limites.get(cid, {})
        containers.append({
            "id": cid[:12], "nome": c.get("Names", ""), "imagem": c.get("Image", ""), "estado": c.get("State", ""),
            "status": c.get("Status", ""), "portas": c.get("Ports", ""), "criado": c.get("RunningFor", ""),
            "limite_memoria": extra.get("memoria", 0), "projeto": extra.get("projeto", ""),
            "cpu": uso.get(cid, {}).get("cpu", ""), "uso_memoria": uso.get(cid, {}).get("mem", ""),
        })
    imagens = [{"id": i.get("ID", ""), "nome": f'{i.get("Repository")}:{i.get("Tag")}', "tamanho": i.get("Size", ""),
                "criada": i.get("CreatedSince", "")}
               for i in json_linhas(rodar(["docker", "images", "--format", "{{json .}}"])[1])]
    volumes = [{"nome": v.get("Name", ""), "driver": v.get("Driver", "")}
               for v in json_linhas(rodar(["docker", "volume", "ls", "--format", "{{json .}}"])[1])]
    projetos = []
    cod, txt = rodar(["docker", "compose", "ls", "-a", "--format", "json"])
    if cod == 0 and txt.startswith("["):
        for p in json.loads(txt):
            projetos.append({"nome": p.get("Name", ""), "status": p.get("Status", ""), "arquivos": p.get("ConfigFiles", "")})
    return {"ligado": True, "servico": "active", "containers": containers, "imagens": imagens,
            "volumes": volumes, "projetos": projetos, "portainer": CONF["portainer_url"]}


def arquivos_compose():
    """Arquivos docker-compose do aluno (projetos e pastas conhecidas)."""
    achados = set()
    for base in [PROJETOS, HOME]:
        if not base.is_dir():
            continue
        prof_max = 4 if base == PROJETOS else 1
        for raiz, dirs, arqs in os.walk(base):
            prof = len(Path(raiz).relative_to(base).parts)
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("node_modules", "venv", ".venv")
                       and prof < prof_max]
            for a in arqs:
                if re.fullmatch(r"(docker-)?compose(\.[\w-]+)?\.ya?ml", a):
                    achados.add(str(Path(raiz) / a))
    return sorted(achados)


def acao_docker(d):
    acao = d.get("acao")
    if acao == "ligar":
        ok_ou_erro(rodar(["systemctl", "start", "docker.service"], timeout=90))
        return "Docker ligado."
    if acao in ("start", "stop", "restart", "rm"):
        alvo = d.get("container", "")
        if not REF_OK.match(alvo):
            raise Erro("Container inválido.")
        cmd = ["docker", "rm", "-f", alvo] if acao == "rm" else ["docker", acao, alvo]
        ok_ou_erro(rodar(cmd, timeout=120))
        return {"start": "Container iniciado.", "stop": "Container parado.", "restart": "Container reiniciado.",
                "rm": "Container apagado."}[acao]
    if acao == "logs":
        alvo = d.get("container", "")
        if not REF_OK.match(alvo):
            raise Erro("Container inválido.")
        return rodar(["docker", "logs", "--tail", "300", "--timestamps", alvo], timeout=30)[1] or "(sem logs)"
    if acao == "rmi":
        img = d.get("imagem", "")
        if not REF_OK.match(img):
            raise Erro("Imagem inválida.")
        ok_ou_erro(rodar(["docker", "rmi", img], timeout=120))
        return "Imagem apagada."
    if acao == "pull":
        img = d.get("imagem", "").strip()
        if not REF_OK.match(img):
            raise Erro("Nome de imagem inválido (ex.: nginx:alpine).")
        return ok_ou_erro(rodar(["docker", "pull", img], timeout=900))[-2000:]
    if acao == "run":
        img = d.get("imagem", "").strip()
        nome = d.get("nome", "").strip()
        if not REF_OK.match(img):
            raise Erro("Informe a imagem (ex.: nginx:alpine).")
        cmd = ["docker", "run", "-d"]
        if nome:
            if not NOME_OK.match(nome):
                raise Erro("Nome inválido: use letras, números, - _ .")
            cmd += ["--name", nome]
        for p in [x.strip() for x in d.get("portas", "").replace(";", ",").split(",") if x.strip()]:
            if not PORTAS_OK.match(p):
                raise Erro(f"Porta inválida: {p} (use PC:CONTAINER, ex.: 8081:80)")
            cmd += ["-p", p]
        mem = d.get("memoria", "").strip()
        if mem:
            if not MEM_OK.match(mem):
                raise Erro("Memória inválida (ex.: 512m ou 1g).")
            cmd += ["--memory", mem, "--memory-swap", mem]
        for e in [x.strip() for x in d.get("env", "").splitlines() if x.strip()]:
            if "=" not in e or e.startswith("="):
                raise Erro(f"Variável inválida: {e} (use NOME=valor)")
            cmd += ["-e", e]
        if d.get("reiniciar"):
            cmd += ["--restart", "unless-stopped"]
        cmd.append(img)
        return "Container criado: " + ok_ou_erro(rodar(cmd, timeout=900))[-200:]
    if acao in ("compose_up", "compose_down", "compose_ver"):
        arq = arquivo_permitido(d.get("arquivo", ""))
        if not arq.is_file():
            raise Erro("Arquivo compose não encontrado.")
        base = ["docker", "compose", "-f", str(arq)]
        if acao == "compose_ver":
            return arq.read_text(errors="replace")
        cmd = base + (["up", "-d", "--remove-orphans"] if acao == "compose_up" else ["down"])
        return ok_ou_erro(rodar(cmd, cwd=str(arq.parent), timeout=900))[-3000:] or "OK"
    if acao == "compose_salvar":
        arq = dentro_da_home(d.get("arquivo", ""))
        if not re.fullmatch(r"(docker-)?compose(\.[\w-]+)?\.ya?ml", arq.name):
            raise Erro("O arquivo precisa se chamar docker-compose.yml ou compose.yaml.")
        conteudo = d.get("conteudo", "")
        arq.parent.mkdir(parents=True, exist_ok=True)
        tmp = arq.with_name("." + arq.name + ".painel")
        tmp.write_text(conteudo)
        cod, txt = rodar(["docker", "compose", "-f", str(tmp), "config", "-q"], cwd=str(arq.parent), timeout=60)
        tmp.unlink(missing_ok=True)
        if cod != 0 and docker_ligado():
            raise Erro("O arquivo tem erro e NÃO foi salvo:\n" + txt.replace(str(tmp), arq.name))
        if arq.exists():
            shutil.copy2(arq, arq.with_name(arq.name + ".bak"))
        arq.write_text(conteudo)
        return f"Salvo em {arq} (cópia anterior em {arq.name}.bak)."
    raise Erro("Ação de Docker desconhecida.")


# ---------------------------------------------------------------- Jenkins
class Jenkins:
    def __init__(self):
        self.url = CONF["jenkins_url"].rstrip("/")
        auth = f'{CONF["jenkins_usuario"]}:{CONF["jenkins_senha"]}'.encode()
        self.auth = "Basic " + base64.b64encode(auth).decode()
        self.cookies = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.crumb = None
        self.trava = threading.Lock()

    def req(self, caminho, dados=None, tipo=None, timeout=20):
        cab = {"Authorization": self.auth}
        if tipo:
            cab["Content-Type"] = tipo
        if dados is not None:
            if self.crumb is None:
                c = json.loads(self.req("/crumbIssuer/api/json")[1])
                self.crumb = (c["crumbRequestField"], c["crumb"])
            cab[self.crumb[0]] = self.crumb[1]
        r = urllib.request.Request(self.url + caminho, data=dados, headers=cab, method="POST" if dados is not None else "GET")
        try:
            with self.op.open(r, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 403 and dados is not None and self.crumb is not None:
                self.crumb = None  # crumb vencido: tenta de novo uma vez
                return self.req(caminho, dados, tipo, timeout)
            corpo = e.read().decode("utf-8", "replace")
            raise Erro(f"Jenkins respondeu {e.code}: {re.sub('<[^>]+>', ' ', corpo)[:300].strip()}")
        except (urllib.error.URLError, OSError) as e:
            raise Erro(f"Jenkins não respondeu ({e}).")


JEN = Jenkins()


def caminho_job(nome):
    if not nome or len(nome) > 200 or ".." in nome:
        raise Erro("Job inválido.")
    return "".join("/job/" + urllib.parse.quote(p, safe="") for p in nome.split("/"))


def info_jenkins():
    servico = servico_ativo("jenkins")
    base = {"servico": servico, "url": JEN.url}
    if servico != "active":
        return {**base, "respondendo": False, "jobs": []}
    try:
        _, txt = JEN.req("/api/json?tree=jobs[name,fullName,url,color,_class,lastBuild[number,result,timestamp,duration,building]]")
    except Erro as e:
        return {**base, "respondendo": False, "jobs": [], "erro": str(e)}
    jobs = []
    for j in json.loads(txt).get("jobs", []):
        lb = j.get("lastBuild") or {}
        jobs.append({"nome": j.get("fullName") or j.get("name"), "url": j.get("url"),
                     "tipo": (j.get("_class") or "").split(".")[-1], "cor": j.get("color", ""),
                     "ultimo": lb.get("number"), "resultado": "EM ANDAMENTO" if lb.get("building") else lb.get("result"),
                     "quando": lb.get("timestamp"), "duracao": lb.get("duration")})
    return {**base, "respondendo": True, "jobs": jobs}


MODELO_PIPELINE = """<?xml version='1.1' encoding='UTF-8'?>
<flow-definition plugin="workflow-job">
  <description>Criado pelo Painel DevOps</description>
  <keepDependencies>false</keepDependencies>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition" plugin="workflow-cps">
    <script></script>
    <sandbox>true</sandbox>
  </definition>
  <disabled>false</disabled>
</flow-definition>
"""

SCRIPT_EXEMPLO = """pipeline {
  agent any
  stages {
    stage('Ola') {
      steps {
        sh 'echo "Ola do Jenkins!"'
      }
    }
  }
}
"""


def acao_jenkins(d):
    acao = d.get("acao")
    if acao in ("ligar", "desligar"):
        ok_ou_erro(rodar(["systemctl", "start" if acao == "ligar" else "stop", "jenkins.service"], timeout=900))
        return "Jenkins ligado (pode levar 1 minuto para abrir)." if acao == "ligar" else "Jenkins desligado."
    nome = d.get("job", "").strip()
    if acao == "criar":
        if not NOME_OK.match(nome):
            raise Erro("Nome do job inválido: use letras, números, - _ .")
        raiz = ET.fromstring(MODELO_PIPELINE)
        raiz.find("./definition/script").text = d.get("script") or SCRIPT_EXEMPLO
        xml = b"<?xml version='1.1' encoding='UTF-8'?>\n" + ET.tostring(raiz)
        JEN.req("/createItem?name=" + urllib.parse.quote(nome, safe=""), xml, "application/xml")
        return f"Pipeline '{nome}' criado."
    cj = caminho_job(nome)
    if acao == "construir":
        JEN.req(cj + "/build?delay=0sec", b"")
        return f"Construção de '{nome}' iniciada."
    if acao == "console":
        n = str(d.get("numero") or "lastBuild")
        if n != "lastBuild" and not n.isdigit():
            raise Erro("Número de build inválido.")
        _, txt = JEN.req(f"{cj}/{n}/consoleText", timeout=30)
        return txt[-20000:]
    if acao == "ver_script":
        _, xml = JEN.req(cj + "/config.xml")
        s = ET.fromstring(xml).find("./definition/script")
        if s is None:
            raise Erro("Este job não é um Pipeline com script (ex.: Freestyle ou script vindo do Git). Edite pelo Jenkins.")
        return s.text or ""
    if acao == "salvar_script":
        _, xml = JEN.req(cj + "/config.xml")
        raiz = ET.fromstring(xml)
        s = raiz.find("./definition/script")
        if s is None:
            raise Erro("Este job não tem script editável aqui.")
        s.text = d.get("script", "")
        JEN.req(cj + "/config.xml", b"<?xml version='1.1' encoding='UTF-8'?>\n" + ET.tostring(raiz), "application/xml")
        return "Script salvo."
    if acao == "apagar":
        JEN.req(cj + "/doDelete", b"")
        return f"Job '{nome}' apagado."
    raise Erro("Ação de Jenkins desconhecida.")


# ---------------------------------------------------------------- Git
def repos_git():
    achados = set()
    candidatos = [PROJETOS, HOME / "Área de Trabalho", HOME / "Desktop", HOME]
    for c in vscode_recentes():
        candidatos.append(Path(c["caminho"]))
    for base in candidatos:
        try:
            base = base.resolve()
        except OSError:
            continue
        if not base.is_dir() or (base != HOME and HOME not in base.parents):
            continue
        prof_max = 0 if base == HOME else 3
        for raiz, dirs, _ in os.walk(base):
            prof = len(Path(raiz).relative_to(base).parts)
            if ".git" in dirs:
                achados.add(raiz)
                dirs[:] = []
                continue
            dirs[:] = [x for x in dirs if not x.startswith(".") and x not in ("node_modules", "venv", ".venv")
                       and prof < prof_max]
    return sorted(achados)


def info_repo(caminho):
    g = ["git", "-C", caminho]
    branch = rodar(g + ["branch", "--show-current"])[1] or "(sem branch)"
    status = rodar(g + ["status", "--porcelain=v1", "-b"])[1].splitlines()
    cab = status[0] if status and status[0].startswith("##") else ""
    mudancas = [{"codigo": l[:2], "arquivo": l[3:]} for l in status if not l.startswith("##")]
    log = []
    cod, txt = rodar(g + ["log", "-8", "--date=format:%d/%m %H:%M", "--pretty=format:%h\x1f%ad\x1f%an\x1f%s"])
    if cod == 0:
        for l in txt.splitlines():
            p = l.split("\x1f")
            if len(p) == 4:
                log.append({"hash": p[0], "data": p[1], "autor": p[2], "msg": p[3]})
    branches = [b.strip() for b in rodar(g + ["branch", "--format=%(refname:short)"])[1].splitlines() if b.strip()]
    remoto = rodar(g + ["remote", "get-url", "origin"])[1] if rodar(g + ["remote"])[1] else ""
    m = re.search(r"\[(.*)\]", cab)
    return {"caminho": caminho, "nome": os.path.basename(caminho), "branch": branch, "branches": branches,
            "mudancas": mudancas, "log": log, "remoto": re.sub(r"//[^/@]+@", "//", remoto),
            "sincronia": m.group(1) if m else ""}


def info_git():
    nome = rodar(["git", "config", "--global", "user.name"])[1]
    email = rodar(["git", "config", "--global", "user.email"])[1]
    return {"usuario": nome, "email": email, "pasta_projetos": str(PROJETOS),
            "repos": [info_repo(r) for r in repos_git()]}


def acao_git(d):
    acao = d.get("acao")
    if acao == "configurar":
        nome, email = d.get("nome", "").strip(), d.get("email", "").strip()
        if not nome or not re.fullmatch(r"[^@\s]+@[^@\s]+", email):
            raise Erro("Informe nome e um e-mail válido.")
        rodar(["git", "config", "--global", "user.name", nome])
        rodar(["git", "config", "--global", "user.email", email])
        return "Identidade do Git salva."
    if acao == "novo":
        nome = d.get("nome", "").strip()
        if not NOME_OK.match(nome):
            raise Erro("Nome inválido: use letras, números, - _ .")
        pasta = PROJETOS / nome
        if pasta.exists():
            raise Erro("Já existe uma pasta com esse nome em ~/projetos.")
        pasta.mkdir(parents=True)
        ok_ou_erro(rodar(["git", "init", "-q", "-b", "main", str(pasta)]))
        (pasta / "README.md").write_text(f"# {nome}\n")
        return f"Projeto criado em {pasta}."
    if acao == "clonar":
        url = d.get("url", "").strip()
        if not re.fullmatch(r"(https://|git@)[\w.@:/~\-]+?(\.git)?/?", url):
            raise Erro("URL inválida (ex.: https://github.com/usuario/repositorio.git).")
        PROJETOS.mkdir(exist_ok=True)
        return ok_ou_erro(rodar(["git", "clone", url], cwd=str(PROJETOS), timeout=600)) or "Repositório clonado."
    repo = dentro_da_home(d.get("repo", ""))
    if not (repo / ".git").exists():
        raise Erro("Isto não é um repositório Git.")
    g = ["git", "-C", str(repo)]
    if acao == "commit":
        msg = d.get("mensagem", "").strip()
        if not msg:
            raise Erro("Escreva a mensagem do commit.")
        ok_ou_erro(rodar(g + ["add", "-A"]))
        return ok_ou_erro(rodar(g + ["commit", "-m", msg]))
    if acao in ("pull", "push"):
        cmd = g + ([acao] if acao == "pull" else ["push", "-u", "origin", "HEAD"])
        cod, txt = rodar(cmd, timeout=300)
        if cod != 0 and ("terminal prompts disabled" in txt or "could not read Username" in txt):
            raise Erro("O GitHub pediu login. Faça este push/pull uma vez pelo terminal (botão Terminal) com seu token.")
        return ok_ou_erro((cod, txt)) or "OK"
    if acao == "checkout":
        b = d.get("branch", "").strip()
        if not BRANCH_OK.match(b):
            raise Erro("Nome de branch inválido.")
        existe = b in [x.strip() for x in rodar(g + ["branch", "--format=%(refname:short)"])[1].splitlines()]
        return ok_ou_erro(rodar(g + (["switch", b] if existe else ["switch", "-c", b]))) or f"Agora na branch {b}."
    if acao == "diff":
        return rodar(g + ["diff", "--stat"])[1] + "\n\n" + rodar(g + ["diff"])[1][:20000] or "(sem diferenças)"
    raise Erro("Ação de Git desconhecida.")


# ---------------------------------------------------------------- VS Code
def vscode_recentes():
    db = HOME / ".config" / "Code" / "User" / "globalStorage" / "state.vscdb"
    itens = []
    if db.exists():
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
            row = con.execute("SELECT value FROM ItemTable WHERE key='history.recentlyOpenedPathsList'").fetchone()
            con.close()
            for e in (json.loads(row[0]).get("entries", []) if row else []):
                uri = e.get("folderUri") or e.get("fileUri") or (e.get("workspace") or {}).get("configPath")
                if uri and uri.startswith("file://"):
                    cam = urllib.parse.unquote(uri[7:])
                    itens.append({"caminho": cam, "tipo": "pasta" if e.get("folderUri") else "arquivo",
                                  "existe": os.path.exists(cam)})
        except Exception:
            pass
    return itens[:25]


def info_vscode():
    ext = rodar(["code", "--list-extensions"], timeout=60)[1].splitlines()
    return {"recentes": vscode_recentes(), "extensoes": [e for e in ext if "." in e]}


def acao_abrir(d):
    acao = d.get("acao")
    if acao == "url":
        url = d.get("url", "")
        if not re.match(r"^http://(localhost|127\.0\.0\.1):\d+(/.*)?$", url):
            raise Erro("Endereço não permitido.")
        lancar(["firefox", url])
        return "Abrindo no navegador."
    if acao == "portainer":
        lancar(["/usr/local/bin/abrir-portainer"])
        return "Abrindo o Portainer (pode levar alguns segundos na primeira vez)."
    caminho = dentro_da_home(d.get("caminho", str(PROJETOS)))
    if acao == "vscode":
        lancar(["code", str(caminho)])
        return "Abrindo no VS Code."
    if acao == "terminal":
        pasta = caminho if caminho.is_dir() else caminho.parent
        lancar(["xfce4-terminal", f"--working-directory={pasta}"])
        return "Abrindo o terminal."
    if acao == "pasta":
        lancar(["thunar", str(caminho if caminho.is_dir() else caminho.parent)])
        return "Abrindo a pasta."
    raise Erro("Ação desconhecida.")


# ---------------------------------------------------------------- Sistema
def info_sistema():
    mem = {}
    for l in Path("/proc/meminfo").read_text().splitlines():
        k, v = l.split(":", 1)
        mem[k] = int(v.split()[0]) // 1024
    disco = shutil.disk_usage("/")
    carga = os.getloadavg()
    procs = []
    cod, txt = rodar(["ps", "-eo", "pid=,user=,rss=,pcpu=,etime=,comm=", "--sort=-rss"])
    for l in txt.splitlines()[:15]:
        p = l.split(None, 5)
        if len(p) == 6:
            procs.append({"pid": int(p[0]), "usuario": p[1], "mem_mb": round(int(p[2]) / 1024), "cpu": p[3],
                          "tempo": p[4], "nome": p[5], "seu": p[1] == os.environ.get("USER", HOME.name)})
    servicos = {s: servico_ativo(s) for s in ("docker", "jenkins", "NetworkManager", "lightdm")}
    return {"mem_total": mem.get("MemTotal", 0), "mem_disponivel": mem.get("MemAvailable", 0),
            "swap_total": mem.get("SwapTotal", 0), "swap_livre": mem.get("SwapFree", 0),
            "disco_total": disco.total // 2**30, "disco_usado": (disco.total - disco.free) // 2**30,
            "carga": [round(x, 2) for x in carga], "cpus": os.cpu_count(), "processos": procs, "servicos": servicos}


def acao_sistema(d):
    if d.get("acao") == "encerrar":
        pid = int(d.get("pid", 0))
        if pid <= 1 or pid == os.getpid():
            raise Erro("Processo inválido.")
        try:
            dono = os.stat(f"/proc/{pid}").st_uid
        except FileNotFoundError:
            raise Erro("Esse processo já terminou.")
        if dono != os.getuid():
            raise Erro("Só dá para encerrar processos seus.")
        os.kill(pid, signal.SIGTERM)
        return "Processo encerrado."
    raise Erro("Ação desconhecida.")


# ---------------------------------------------------------------- resumo
def resumo():
    s = info_sistema()
    dk = {"ligado": docker_ligado()}
    if dk["ligado"]:
        cont = json_linhas(rodar(["docker", "ps", "-a", "--format", "{{json .}}"])[1])
        dk.update(total=len(cont), rodando=sum(1 for c in cont if c.get("State") == "running"))
    j = info_jenkins()
    jobs = j.get("jobs", [])
    repos = repos_git()
    pend = 0
    for r in repos:
        pend += 1 if rodar(["git", "-C", r, "status", "--porcelain"])[1] else 0
    return {"sistema": s, "docker": dk,
            "jenkins": {"servico": j["servico"], "respondendo": j.get("respondendo"), "jobs": len(jobs),
                        "falhas": sum(1 for x in jobs if x.get("resultado") == "FAILURE"),
                        "sucessos": sum(1 for x in jobs if x.get("resultado") == "SUCCESS")},
            "git": {"repos": len(repos), "com_mudancas": pend},
            "vscode": {"recentes": len(vscode_recentes())}}


GETS = {"/api/resumo": resumo, "/api/docker": info_docker, "/api/jenkins": info_jenkins, "/api/git": info_git,
        "/api/vscode": info_vscode, "/api/sistema": info_sistema,
        "/api/compose-arquivos": lambda: {"arquivos": arquivos_compose()},
        "/api/modelo-pipeline": lambda: {"script": SCRIPT_EXEMPLO}}
POSTS = {"/api/docker": acao_docker, "/api/jenkins": acao_jenkins, "/api/git": acao_git,
         "/api/abrir": acao_abrir, "/api/sistema": acao_sistema}


class Handler(BaseHTTPRequestHandler):
    server_version = "PainelDevOps/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def responder(self, codigo, corpo, tipo="application/json; charset=utf-8"):
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(dados)

    def host_ok(self):
        if self.headers.get("Host", "") not in HOSTS_OK:
            self.responder(403, {"erro": "Acesso permitido só por http://localhost:%d" % PORTA})
            return False
        return True

    def do_GET(self):
        if not self.host_ok():
            return
        caminho = urllib.parse.urlparse(self.path).path
        if caminho == "/saude":
            return self.responder(200, {"ok": True})
        if caminho in ("/", "/index.html"):
            html = (AQUI / "index.html").read_text().replace("__TOKEN__", TOKEN)
            return self.responder(200, html.encode(), "text/html; charset=utf-8")
        f = GETS.get(caminho)
        if not f:
            return self.responder(404, {"erro": "não encontrado"})
        try:
            self.responder(200, f())
        except Erro as e:
            self.responder(400, {"erro": str(e)})
        except Exception as e:  # nunca derruba o painel
            self.responder(500, {"erro": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        if not self.host_ok():
            return
        if not secrets.compare_digest(self.headers.get("X-Painel-Token", ""), TOKEN):
            return self.responder(403, {"erro": "Token inválido. Recarregue a página do painel."})
        f = POSTS.get(urllib.parse.urlparse(self.path).path)
        if not f:
            return self.responder(404, {"erro": "não encontrado"})
        try:
            tam = int(self.headers.get("Content-Length", "0"))
            if tam > 2_000_000:
                raise Erro("Dados grandes demais.")
            dados = json.loads(self.rfile.read(tam) or b"{}")
            self.responder(200, {"ok": True, "resultado": f(dados)})
        except Erro as e:
            self.responder(400, {"erro": str(e)})
        except Exception as e:
            self.responder(500, {"erro": f"{type(e).__name__}: {e}"})


def main():
    os.environ["GIT_TERMINAL_PROMPT"] = "0"
    srv = ThreadingHTTPServer(("127.0.0.1", PORTA), Handler)
    srv.daemon_threads = True
    print(f"Painel DevOps em http://localhost:{PORTA}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
