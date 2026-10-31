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
CONF = {"jenkins_url": "http://localhost:8080", "jenkins_usuario": "aluno", "jenkins_senha": "devops"}
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


HIST = {"t": [], "cpu": [], "mem": [], "max": 120}


def _ler_cpu():
    v = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
    ocioso = v[3] + (v[4] if len(v) > 4 else 0)
    return sum(v), ocioso


def amostrador():
    ant = _ler_cpu()
    while True:
        time.sleep(5)
        try:
            atual = _ler_cpu()
            total, ocioso = atual[0] - ant[0], atual[1] - ant[1]
            ant = atual
            cpu = round(100 * (total - ocioso) / total, 1) if total else 0
            mem = {}
            for l in Path("/proc/meminfo").read_text().splitlines():
                k, val = l.split(":", 1)
                mem[k] = int(val.split()[0]) // 1024
            for k, val in (("t", int(time.time() * 1000)), ("cpu", cpu),
                           ("mem", mem["MemTotal"] - mem["MemAvailable"])):
                HIST[k].append(val)
                del HIST[k][:-HIST["max"]]
        except Exception:
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
            "volumes": volumes, "projetos": projetos,
            "dockerfiles": [str(r) for r, a in _pastas_projetos() if "Dockerfile" in a]}


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
    if acao == "terminal":
        alvo = d.get("container", "")
        if not REF_OK.match(alvo):
            raise Erro("Container inválido.")
        lancar(["xfce4-terminal", f"--title=Terminal do container {alvo}", "-x", "docker", "exec", "-it", alvo,
                "sh", "-c", "command -v bash >/dev/null && exec bash || exec sh"])
        return "Abrindo um terminal dentro do container."
    if acao == "volume_criar":
        nome = d.get("nome", "").strip()
        if not NOME_OK.match(nome):
            raise Erro("Nome de volume inválido.")
        ok_ou_erro(rodar(["docker", "volume", "create", nome]))
        return f"Volume '{nome}' criado."
    if acao == "volume_rm":
        nome = d.get("nome", "").strip()
        if not NOME_OK.match(nome):
            raise Erro("Volume inválido.")
        ok_ou_erro(rodar(["docker", "volume", "rm", nome]))
        return f"Volume '{nome}' apagado."
    if acao == "limpar":
        return ok_ou_erro(rodar(["docker", "system", "prune", "-f"], timeout=300))[-1500:]
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
        for v in [x.strip() for x in d.get("volumes", "").replace(";", ",").split(",") if x.strip()]:
            orig, _, dest = v.partition(":")
            if not dest.startswith("/") or not (NOME_OK.match(orig) or orig.startswith(("/home/", "~/"))):
                raise Erro(f"Volume inválido: {v} (use nome-do-volume:/caminho ou ~/pasta:/caminho)")
            if orig.startswith("~/"):
                orig = str(dentro_da_home(orig))
            cmd += ["-v", f"{orig}:{dest}"]
        comando = d.get("comando", "").strip()
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
        if comando:
            import shlex
            cmd += shlex.split(comando)
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
        _, txt = JEN.req("/api/json?tree=jobs[name,fullName,url,color,_class,lastBuild[number,result,timestamp,duration,building],"
                         "builds[number,result,timestamp,duration,building]{0,15}]")
    except Erro as e:
        return {**base, "respondendo": False, "jobs": [], "erro": str(e)}
    jobs = []
    for j in json.loads(txt).get("jobs", []):
        lb = j.get("lastBuild") or {}
        jobs.append({"nome": j.get("fullName") or j.get("name"), "url": j.get("url"),
                     "tipo": (j.get("_class") or "").split(".")[-1], "cor": j.get("color", ""),
                     "ultimo": lb.get("number"), "resultado": "EM ANDAMENTO" if lb.get("building") else lb.get("result"),
                     "quando": lb.get("timestamp"), "duracao": lb.get("duration"),
                     "historico": [{"n": b.get("number"), "r": "EM ANDAMENTO" if b.get("building") else b.get("result"),
                                    "t": b.get("timestamp"), "d": b.get("duration")} for b in (j.get("builds") or [])]})
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
    if acao == "etapas":
        try:
            _, txt = JEN.req(cj + "/lastBuild/wfapi/describe", timeout=20)
        except Erro:
            return {"etapas": []}
        dd = json.loads(txt)
        return {"numero": dd.get("id"), "status": dd.get("status"),
                "etapas": [{"nome": st.get("name"), "status": st.get("status"), "duracao": st.get("durationMillis", 0)}
                           for st in dd.get("stages", [])]}
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


def commits_por_dia(repos, dias=14):
    import datetime
    hoje = datetime.date.today()
    cont = {(hoje - datetime.timedelta(days=i)).isoformat(): 0 for i in range(dias - 1, -1, -1)}
    for r in repos:
        cod, txt = rodar(["git", "-C", r, "log", "--all", f"--since={dias}.days", "--format=%ad", "--date=short"])
        for l in txt.splitlines():
            if l in cont:
                cont[l] += 1
    return [{"dia": k, "n": v} for k, v in cont.items()]


def info_git():
    nome = rodar(["git", "config", "--global", "user.name"])[1]
    email = rodar(["git", "config", "--global", "user.email"])[1]
    repos = repos_git()
    return {"usuario": nome, "email": email, "pasta_projetos": str(PROJETOS),
            "repos": [info_repo(r) for r in repos], "por_dia": commits_por_dia(repos)}


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
        arquivos = d.get("arquivos")
        if arquivos:
            for a in arquivos:
                alvo = (repo / a).resolve()
                if alvo != repo and repo not in alvo.parents:
                    raise Erro(f"Arquivo fora do repositório: {a}")
            ok_ou_erro(rodar(g + ["add", "-A", "--"] + list(arquivos)))
        else:
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
    pastas = sorted(str(p) for p in PROJETOS.iterdir() if p.is_dir() and not p.name.startswith(".")) \
        if PROJETOS.is_dir() else []
    return {"recentes": vscode_recentes(), "extensoes": [e for e in ext if "." in e], "pastas": pastas}


def acao_abrir(d):
    acao = d.get("acao")
    if acao == "url":
        url = d.get("url", "")
        if not re.match(r"^http://(localhost|127\.0\.0\.1):\d+(/.*)?$", url):
            raise Erro("Endereço não permitido.")
        lancar(["firefox", url])
        return "Abrindo no navegador."
    caminho = dentro_da_home(d.get("caminho", str(PROJETOS)))
    if acao == "novo_arquivo":
        nome = d.get("nome", "").strip()
        if not re.fullmatch(r"[\w.\- ]{1,100}", nome):
            raise Erro("Nome de arquivo inválido.")
        alvo = caminho / nome
        if not alvo.exists():
            alvo.write_text(d.get("conteudo", ""))
        lancar(["code", str(caminho), str(alvo)])
        return f"Abrindo {nome} no VS Code."
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


# ---------------------------------------------------------------- tarefas (comandos longos com saída ao vivo)
TAREFAS = {}
TAREFAS_TRAVA = threading.Lock()
PROCESSOS = {}


def parar_tarefa(d):
    p = PROCESSOS.get(d.get("id", ""))
    if not p:
        return "A tarefa já terminou."
    try:
        os.killpg(p.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    return "Tarefa interrompida."


def iniciar_tarefa(ferramenta, titulo, cmd, cwd=None, env_extra=None):
    tid = secrets.token_hex(6)
    t = {"id": tid, "ferramenta": ferramenta, "titulo": titulo, "comando": " ".join(cmd), "pasta": cwd or "",
         "linhas": [], "fim": False, "codigo": None, "inicio": int(time.time() * 1000), "duracao": 0}
    with TAREFAS_TRAVA:
        TAREFAS[tid] = t
        for velho in sorted(TAREFAS.values(), key=lambda x: x["inicio"])[:-60]:
            TAREFAS.pop(velho["id"], None)

    def correr():
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", ANSIBLE_FORCE_COLOR="0", PYTHONUNBUFFERED="1",
                   TF_IN_AUTOMATION="1", **(env_extra or {}))
        try:
            p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 text=True, errors="replace", env=env, bufsize=1, start_new_session=True)
            PROCESSOS[tid] = p
            for linha in p.stdout:
                t["linhas"].append(re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", linha.rstrip("\n")))
                if len(t["linhas"]) > 5000:
                    del t["linhas"][:1000]
            t["codigo"] = p.wait()
        except FileNotFoundError:
            t["linhas"].append(f"pasta não encontrada: {cwd}" if cwd and not os.path.isdir(cwd)
                               else f"comando não encontrado: {cmd[0]}")
            t["codigo"] = 127
        except Exception as e:
            t["linhas"].append(f"erro: {e}")
            t["codigo"] = 1
        t["duracao"] = int(time.time() * 1000) - t["inicio"]
        t["fim"] = True
        PROCESSOS.pop(tid, None)

    threading.Thread(target=correr, daemon=True).start()
    return {"tarefa": tid, "titulo": titulo}


def ver_tarefa(q):
    t = TAREFAS.get(q.get("id", [""])[0])
    if not t:
        raise Erro("Tarefa não encontrada.")
    desde = int(q.get("desde", ["0"])[0])
    return {**{k: t[k] for k in ("id", "ferramenta", "titulo", "comando", "fim", "codigo", "inicio", "duracao")},
            "linhas": t["linhas"][desde:], "total": len(t["linhas"])}


def listar_tarefas():
    return {"tarefas": [{k: t[k] for k in ("id", "ferramenta", "titulo", "fim", "codigo", "inicio", "duracao")}
                        for t in sorted(TAREFAS.values(), key=lambda x: -x["inicio"])][:30]}


def acao_executar(d):
    """Comandos longos das ferramentas, sempre com saída ao vivo."""
    f, a = d.get("ferramenta"), d.get("acao")
    if f == "docker":
        if a == "pull":
            img = d.get("imagem", "").strip()
            if not REF_OK.match(img):
                raise Erro("Nome de imagem inválido (ex.: nginx:alpine).")
            return iniciar_tarefa("docker", f"docker pull {img}", ["docker", "pull", img])
        if a in ("compose_up", "compose_down", "compose_logs"):
            arq = arquivo_permitido(d.get("arquivo", ""))
            if not arq.is_file():
                raise Erro("Arquivo compose não encontrado.")
            extra = {"compose_up": ["up", "-d", "--remove-orphans"], "compose_down": ["down"],
                     "compose_logs": ["logs", "--tail", "200", "--no-color"]}[a]
            return iniciar_tarefa("docker", f"docker compose {' '.join(extra[:2])} ({arq.parent.name})",
                                  ["docker", "compose", "-f", str(arq)] + extra, cwd=str(arq.parent))
        if a == "build":
            pasta = dentro_da_home(d.get("pasta", ""))
            tag = d.get("tag", "").strip() or pasta.name.lower()
            if not REF_OK.match(tag) or not (pasta / "Dockerfile").is_file():
                raise Erro("Pasta sem Dockerfile ou nome de imagem inválido.")
            return iniciar_tarefa("docker", f"docker build -t {tag}", ["docker", "build", "-t", tag, "."], cwd=str(pasta))
    if f == "git":
        if a == "clonar":
            url = d.get("url", "").strip()
            if not re.fullmatch(r"(https://|git@)[\w.@:/~\-]+?(\.git)?/?", url):
                raise Erro("URL inválida (ex.: https://github.com/usuario/repositorio.git).")
            PROJETOS.mkdir(exist_ok=True)
            return iniciar_tarefa("git", f"git clone {url}", ["git", "clone", "--progress", url], cwd=str(PROJETOS))
        repo = dentro_da_home(d.get("repo", ""))
        if not (repo / ".git").exists():
            raise Erro("Isto não é um repositório Git.")
        if a in ("pull", "push"):
            cmd = ["git", a] if a == "pull" else ["git", "push", "-u", "origin", "HEAD"]
            return iniciar_tarefa("git", f"git {a} ({repo.name})", cmd, cwd=str(repo))
    if f == "ansible":
        pb = dentro_da_home(d.get("playbook", ""))
        if a in ("rodar", "checar", "simular"):
            if not pb.is_file():
                raise Erro("Playbook não encontrado.")
            inv = pb.parent / "inventario.ini"
            cmd = ["ansible-playbook", "-i", str(inv) if inv.is_file() else "localhost,", "-c", "local", pb.name]
            cmd += {"rodar": [], "checar": ["--syntax-check"], "simular": ["--check", "--diff"]}[a]
            return iniciar_tarefa("ansible", f"ansible-playbook {pb.name}" + ("" if a == "rodar" else f" ({a})"),
                                  cmd, cwd=str(pb.parent))
        if a == "adhoc":
            mod, args = d.get("modulo", "ping").strip(), d.get("args", "").strip()
            if not re.fullmatch(r"[a-z0-9_.]{1,80}", mod):
                raise Erro("Módulo inválido.")
            cmd = ["ansible", "localhost", "-c", "local", "-m", mod] + (["-a", args] if args else [])
            return iniciar_tarefa("ansible", f"ansible -m {mod}", cmd, cwd=str(HOME))
    if f == "terraform":
        pasta = dentro_da_home(d.get("pasta", ""))
        if not any(pasta.glob("*.tf")):
            raise Erro("Esta pasta não tem arquivos .tf.")
        cmds = {"init": ["init", "-input=false", "-no-color"], "validate": ["validate", "-no-color"],
                "plan": ["plan", "-input=false", "-no-color"], "apply": ["apply", "-auto-approve", "-input=false", "-no-color"],
                "destroy": ["destroy", "-auto-approve", "-input=false", "-no-color"], "fmt": ["fmt", "-diff", "-no-color"],
                "output": ["output", "-no-color"], "state": ["state", "list"]}
        if a not in cmds:
            raise Erro("Ação do Terraform desconhecida.")
        return iniciar_tarefa("terraform", f"terraform {a} ({pasta.name})", ["terraform"] + cmds[a], cwd=str(pasta))
    if f == "python":
        pasta = dentro_da_home(d.get("pasta", ""))
        venv_py = pasta / ".venv" / "bin" / "python"
        py = str(venv_py) if venv_py.exists() else "python3"
        if a == "rodar":
            script = dentro_da_home(d.get("script", ""))
            if script.suffix != ".py" or not script.is_file():
                raise Erro("Escolha um arquivo .py.")
            return iniciar_tarefa("python", f"python {script.name}", [py, "-u", script.name], cwd=str(script.parent))
        if a == "venv":
            return iniciar_tarefa("python", f"criar .venv ({pasta.name})", ["python3", "-m", "venv", ".venv"], cwd=str(pasta))
        if a == "pip":
            pacotes = d.get("pacotes", "").split()
            if not pacotes and (pasta / "requirements.txt").is_file():
                pacotes = ["-r", "requirements.txt"]
            for pk in pacotes:
                if pk != "-r" and not re.fullmatch(r"[A-Za-z0-9_.\-\[\]=<>~!,]+", pk):
                    raise Erro(f"Pacote inválido: {pk}")
            if not venv_py.exists():
                raise Erro("Crie o ambiente (.venv) primeiro.")
            return iniciar_tarefa("python", f"pip install {' '.join(pacotes)}", [py, "-m", "pip", "install"] + pacotes,
                                  cwd=str(pasta))
        if a == "piplist":
            return iniciar_tarefa("python", f"pip list ({pasta.name})", [py, "-m", "pip", "list"], cwd=str(pasta))
    raise Erro("Ação desconhecida.")


# ---------------------------------------------------------------- Ansible, Terraform, Python, arquivos
def _pastas_projetos(prof_max=3):
    if not PROJETOS.is_dir():
        return
    for raiz, dirs, arqs in os.walk(PROJETOS):
        prof = len(Path(raiz).relative_to(PROJETOS).parts)
        dirs[:] = [x for x in dirs if not x.startswith(".") and x not in ("node_modules", "venv", ".venv", "__pycache__")
                   and prof < prof_max]
        yield Path(raiz), arqs


def info_ansible():
    playbooks = []
    for raiz, arqs in _pastas_projetos():
        for a in arqs:
            if a.endswith((".yml", ".yaml")) and not re.fullmatch(r"(docker-)?compose.*", a):
                cam = raiz / a
                try:
                    txt = cam.read_text(errors="replace")[:20000]
                except OSError:
                    continue
                if re.search(r"^\s*-?\s*hosts\s*:", txt, re.M):
                    nome = re.search(r"^\s*-\s*name\s*:\s*(.+)$", txt, re.M)
                    hosts = re.search(r"hosts\s*:\s*(.+)$", txt, re.M)
                    playbooks.append({"arquivo": str(cam), "nome": nome.group(1).strip() if nome else a,
                                      "hosts": hosts.group(1).strip() if hosts else "",
                                      "tarefas": len(re.findall(r"^\s+- name\s*:", txt, re.M))})
    return {"playbooks": playbooks}


def info_terraform():
    projetos = []
    for raiz, arqs in _pastas_projetos():
        tfs = sorted(a for a in arqs if a.endswith(".tf"))
        if not tfs:
            continue
        recursos = []
        estado = raiz / "terraform.tfstate"
        if estado.is_file():
            try:
                for r in json.loads(estado.read_text()).get("resources", []):
                    if r.get("mode") == "managed":
                        recursos.append(f'{r.get("type")}.{r.get("name")}')
            except Exception:
                pass
        projetos.append({"pasta": str(raiz), "nome": raiz.name, "arquivos": tfs,
                         "iniciado": (raiz / ".terraform").is_dir(), "recursos": recursos})
    return {"projetos": projetos}


def info_python():
    projetos = []
    for raiz, arqs in _pastas_projetos(2):
        pys = sorted(a for a in arqs if a.endswith(".py"))
        if not pys and "requirements.txt" not in arqs:
            continue
        projetos.append({"pasta": str(raiz), "nome": raiz.name, "scripts": pys, "venv": (raiz / ".venv").is_dir(),
                         "requirements": "requirements.txt" in arqs})
    return {"projetos": projetos, "versao": rodar(["python3", "--version"])[1]}


_FERR = {"quando": 0, "dados": []}


def info_ferramentas():
    if time.time() - _FERR["quando"] < 600 and _FERR["dados"]:
        return {"ferramentas": _FERR["dados"]}
    lista = [("Docker", ["docker", "--version"]), ("Docker Compose", ["docker", "compose", "version", "--short"]),
             ("Git", ["git", "--version"]), ("VS Code", ["code", "--version"]), ("Ansible", ["ansible", "--version"]),
             ("Terraform", ["terraform", "-version"]), ("Python", ["python3", "--version"]),
             ("Java", ["java", "-version"]), ("Firefox", ["firefox", "--version"])]
    dados = []
    for nome, cmd in lista:
        cod, txt = rodar(cmd, timeout=30)
        dados.append({"nome": nome, "ok": cod == 0, "versao": (txt.splitlines() or [""])[0][:80]})
    try:
        _, v = JEN.req("/login", timeout=5)
        jv = re.search(r"Jenkins ([\d.]+)", v)
        dados.append({"nome": "Jenkins", "ok": True, "versao": "Jenkins " + (jv.group(1) if jv else "")})
    except Erro:
        dados.append({"nome": "Jenkins", "ok": servico_ativo("jenkins") == "active", "versao": "ligando ou desligado"})
    _FERR.update(quando=time.time(), dados=dados)
    return {"ferramentas": dados}


def acao_arquivo(d):
    acao = d.get("acao")
    cam = dentro_da_home(d.get("caminho", "")) if acao in ("ler", "salvar") else None
    if acao == "ler":
        if not cam.is_file():
            return ""
        if cam.stat().st_size > 1_000_000:
            raise Erro("Arquivo grande demais para editar aqui.")
        return cam.read_text(errors="replace")
    if acao == "salvar":
        cam.parent.mkdir(parents=True, exist_ok=True)
        if cam.exists():
            shutil.copy2(cam, cam.with_name(cam.name + ".bak"))
        cam.write_text(d.get("conteudo", ""))
        return f"Salvo: {cam.name}"
    if acao == "projeto":
        nome = d.get("nome", "").strip()
        if not NOME_OK.match(nome):
            raise Erro("Nome inválido: use letras, números, - _ .")
        pasta = PROJETOS / nome
        if pasta.exists() and any(pasta.iterdir()):
            raise Erro(f"Já existe ~/projetos/{nome}. Escolha outro nome.")
        for rel, conteudo in (d.get("arquivos") or {}).items():
            alvo = (pasta / rel).resolve()
            if pasta.resolve() not in alvo.parents:
                raise Erro("Caminho de arquivo inválido.")
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_text(conteudo)
        pasta.mkdir(parents=True, exist_ok=True)
        if d.get("git"):
            rodar(["git", "init", "-q", "-b", "main", str(pasta)])
        return {"pasta": str(pasta), "msg": f"Projeto criado em ~/projetos/{nome}."}
    raise Erro("Ação desconhecida.")


# ---------------------------------------------------------------- resumo
def resumo():
    s = info_sistema()
    dk = {"ligado": docker_ligado()}
    if dk["ligado"]:
        cont = json_linhas(rodar(["docker", "ps", "-a", "--format", "{{json .}}"])[1])
        estados = {}
        for c in cont:
            estados[c.get("State", "?")] = estados.get(c.get("State", "?"), 0) + 1
        dk.update(total=len(cont), rodando=estados.get("running", 0), estados=estados,
                  imagens=len(rodar(["docker", "images", "-q"])[1].split()))
    j = info_jenkins()
    jobs = j.get("jobs", [])
    builds = []
    for x in jobs:
        for b in x.get("historico", []):
            builds.append({"job": x["nome"], **b})
    builds.sort(key=lambda b: b.get("t") or 0)
    repos = repos_git()
    pend = 0
    for r in repos:
        pend += 1 if rodar(["git", "-C", r, "status", "--porcelain"])[1] else 0
    return {"sistema": s, "docker": dk,
            "jenkins": {"servico": j["servico"], "respondendo": j.get("respondendo"), "jobs": len(jobs),
                        "falhas": sum(1 for x in jobs if x.get("resultado") == "FAILURE"),
                        "sucessos": sum(1 for x in jobs if x.get("resultado") == "SUCCESS")},
            "builds": builds[-30:], "historico": {k: HIST[k] for k in ("t", "cpu", "mem")},
            "git": {"repos": len(repos), "com_mudancas": pend, "por_dia": commits_por_dia(repos)},
            "vscode": {"recentes": len(vscode_recentes())},
            "ansible": {"playbooks": len(info_ansible()["playbooks"])},
            "terraform": (lambda t: {"projetos": len(t["projetos"]), "recursos": sum(len(p["recursos"]) for p in t["projetos"])})(info_terraform()),
            "python": {"projetos": len(info_python()["projetos"])},
            "tarefas": listar_tarefas()["tarefas"][:12]}


GETS = {"/api/resumo": resumo, "/api/docker": info_docker, "/api/jenkins": info_jenkins, "/api/git": info_git,
        "/api/vscode": info_vscode, "/api/sistema": info_sistema,
        "/api/compose-arquivos": lambda: {"arquivos": arquivos_compose()},
        "/api/modelo-pipeline": lambda: {"script": SCRIPT_EXEMPLO},
        "/api/historico": lambda: {k: HIST[k] for k in ("t", "cpu", "mem")},
        "/api/ansible": info_ansible, "/api/terraform": info_terraform, "/api/python": info_python,
        "/api/ferramentas": info_ferramentas, "/api/tarefas": listar_tarefas}
GETS_Q = {"/api/tarefa": ver_tarefa}
POSTS = {"/api/docker": acao_docker, "/api/jenkins": acao_jenkins, "/api/git": acao_git,
         "/api/abrir": acao_abrir, "/api/sistema": acao_sistema, "/api/executar": acao_executar,
         "/api/arquivo": acao_arquivo, "/api/tarefa-parar": parar_tarefa}


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
        url = urllib.parse.urlparse(self.path)
        caminho = url.path
        if caminho in GETS_Q:
            try:
                return self.responder(200, GETS_Q[caminho](urllib.parse.parse_qs(url.query)))
            except Erro as e:
                return self.responder(404, {"erro": str(e)})
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
    threading.Thread(target=amostrador, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORTA), Handler)
    srv.daemon_threads = True
    print(f"Painel DevOps em http://localhost:{PORTA}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
