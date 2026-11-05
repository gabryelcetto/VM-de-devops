#!/usr/bin/env python3
"""Painel DevOps: mostra e altera o que o aluno criou no Docker, Jenkins, Git e VS Code.

Roda só em 127.0.0.1 (nada fica visível na rede). Toda ação que altera algo exige o
token da página (cabeçalho X-Painel-Token) e o Host precisa ser localhost: outra página
aberta no navegador não consegue mandar comandos para cá.
Só usa a biblioteca padrão do Python.
"""
import base64
import html as html_mod
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
from concurrent.futures import ThreadPoolExecutor
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

# \Z (e não $): "$" também aceita um "\n" no fim, e um nome com quebra de linha passaria
NOME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}\Z")
REF_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:@\-]{0,254}\Z")
BRANCH_OK = re.compile(r"^(?!-)(?!.*\.\.)[A-Za-z0-9_./\-]{1,100}\Z")
PORTAS_OK = re.compile(r"^(\d{1,5}:\d{1,5}(/(tcp|udp))?)\Z")
MEM_OK = re.compile(r"^\d{1,6}[bkmgBKMG]?\Z")


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
def rodar(cmd, cwd=None, timeout=120, entrada=None, so_saida=False):
    """Executa sem shell; devolve (código, saída+erro). so_saida=True ignora os avisos (stderr),
    para analisar a saída sem misturar mensagens como "warning: ..."."""
    try:
        p = subprocess.run(cmd, cwd=cwd, input=entrada, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout if so_saida else p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, f"comando não encontrado: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "tempo esgotado"


DICAS = [
    (r"port is already allocated|address already in use", "A porta já está sendo usada por outro container ou programa. Pare ou apague quem usa a porta (aba Docker) ou escolha outra porta."),
    (r'The container name "/?([\w.-]+)" is already in use', "Já existe um container chamado {0}. Apague o antigo na aba Docker ou escolha outro nome."),
    (r"Permission denied \(publickey\)", "O GitHub recusou a chave SSH. Em Git > Acesso ao GitHub: gere a chave, copie, cadastre em github.com/settings/keys e clique em Testar conexão."),
    (r"Host key verification failed", "O servidor Git não é conhecido. Para o GitHub isso já vem configurado; confira se o endereço está certo."),
    (r"terminal prompts disabled|could not read Username|Authentication failed", "O GitHub pediu login. Guarde um token em Git > Acesso ao GitHub (endereços https) ou use a chave SSH (endereços git@github.com)."),
    (r"Repository not found|repository '.*' not found|does not appear to be a git repository", "Repositório não encontrado. Confira o endereço; se ele for privado, configure o token ou a chave SSH."),
    (r"\[rejected\].*\(fetch first\)|Updates were rejected because the remote contains work|\(non-fast-forward\)", "O GitHub tem commits que você ainda não tem. Faça Pull primeiro e depois Push de novo."),
    (r"refusing to merge unrelated histories", "O repositório do GitHub foi criado com arquivos próprios (ex.: README) e não tem histórico em comum com o seu. Use ⋯ > Pull juntando históricos."),
    (r"There is no tracking information for the current branch", "Esta branch ainda não foi enviada ao GitHub. Faça Push primeiro: ele liga a branch ao GitHub."),
    (r"CONFLICT \(content\)|Automatic merge failed", "Conflito: o mesmo trecho foi mudado nos dois lados. Abra o projeto no VS Code, escolha o que fica em cada conflito, salve e faça Commit."),
    (r"destination path '([^']+)' already exists", "Já existe a pasta {0} em ~/projetos. Apague ou renomeie a pasta antes de clonar de novo."),
    (r"src refspec \S+ does not match any", "Ainda não existe nenhum commit para enviar. Faça um Commit antes do primeiro Push."),
    (r"Please tell me who you are|empty ident name", "Configure seu nome e e-mail em Git > Acesso ao GitHub antes de fazer commits."),
    (r"ModuleNotFoundError: No module named '([\w.]+)'", "Falta o pacote Python {0}. Na aba Python, use o botão Instalar pacote (ou ponha no requirements.txt)."),
    (r"Failed to query available provider packages|could not connect to registry.terraform.io|failed to request discovery document", "O terraform init precisa de internet para baixar os providers. Confira a conexão da VM."),
    (r"Cannot connect to the Docker daemon|permission denied while trying to connect to the Docker daemon", "O Docker está desligado ou sem permissão. Ligue o Docker na aba Sistema; se for no Jenkins, reinicie o Jenkins."),
    (r"pull access denied|manifest unknown|repository does not exist or may require", "Imagem não encontrada no Docker Hub. Confira o nome e a tag (ex.: nginx:alpine)."),
    (r"Could not resolve host|Temporary failure in name resolution|getaddrinfo|Network is unreachable|i/o timeout|TLS handshake timeout", "Sem conexão com a internet (ou ela caiu no meio). Confira a rede da VM e tente de novo."),
    (r"no space left on device", "Disco cheio. Use Docker > Volumes e redes > Limpar o que não está em uso."),
    (r"(?:yaml|YAML).*line (\d+)|mapping values are not allowed|found character that cannot start any token", "Erro de formatação no YAML (perto da linha {0}). Use espaços para indentar, nunca tab, e confira os dois-pontos."),
    (r"Couldn't find any revision to build|couldn't find remote ref", "A branch informada não existe no repositório. Confira o nome (main ou master)."),
    (r"Unable to find (\S*Jenkinsfile)|Jenkinsfile not found", "O Jenkinsfile não foi encontrado nesse caminho do repositório. Confira o campo Caminho do Jenkinsfile."),
    (r"script returned exit code 127|: not found$|command not found", "Algum comando do script não existe na máquina. Confira a digitação ou instale o programa."),
]


def dicas_para(texto):
    """Dicas em português para erros conhecidos que aparecem em um texto de saída."""
    vistas = []
    for padrao, dica in DICAS:
        m = re.search(padrao, texto or "", re.M)
        if m:
            d = dica.format(*[g or "" for g in m.groups()]) if m.groups() else dica
            if d not in vistas:
                vistas.append(d)
    return vistas


def ok_ou_erro(r):
    cod, txt = r
    if cod != 0:
        raise Erro(txt or f"falhou (código {cod})")
    return txt


def lancar(cmd, cwd=None):
    """Abre um programa gráfico sem esperar (VS Code, terminal, navegador)."""
    try:
        subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except FileNotFoundError:
        raise Erro(f"Programa não encontrado: {cmd[0]}")


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
    """Docker respondendo. Atenção: falar com o Docker LIGA o Docker (ele liga no primeiro uso);
    use só onde o aluno quer usar o Docker (aba Docker). Para só mostrar a situação, docker_ativo()."""
    return rodar(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=30)[0] == 0


def docker_ativo():
    """O Docker já está ligado? (não liga o Docker só para perguntar: economiza ~150 MB de memória)"""
    return servico_ativo("docker") == "active"


# imagens "de base": sem comando, o container abre um shell/interpretador e para na hora
IMAGENS_BASE = {"python", "ubuntu", "debian", "alpine", "busybox", "node", "fedora", "centos", "rockylinux", "almalinux",
                "archlinux", "golang", "openjdk", "eclipse-temurin", "ruby", "php", "rust", "gcc", "amazonlinux", "oraclelinux"}


# "docker stats" demora ~2 s (mede duas vezes para calcular a CPU). Para a aba Docker abrir na hora,
# o uso de CPU/memória vem da última medição (até 20 s atrás) e uma nova é feita em segundo plano.
_USO = {"quando": 0.0, "dados": {}, "medindo": False}
_USO_TRAVA = threading.Lock()


def _medir_uso():
    try:
        dados = {}
        for s in json_linhas(rodar(["docker", "stats", "--no-stream", "--no-trunc", "--format", "{{json .}}"], timeout=40)[1]):
            dados[s.get("ID", "")] = {"cpu": s.get("CPUPerc", ""), "mem": s.get("MemUsage", "")}
        with _USO_TRAVA:
            _USO.update(dados=dados, quando=time.time())
    finally:
        with _USO_TRAVA:
            _USO["medindo"] = False


def uso_containers():
    with _USO_TRAVA:
        dados = _USO["dados"]
        medir = time.time() - _USO["quando"] > 20 and not _USO["medindo"]
        if medir:
            _USO["medindo"] = True
    if medir:
        t = threading.Thread(target=_medir_uso, daemon=True)
        t.start()
        if not dados:  # primeira vez: espera, para não mostrar a coluna de uso vazia
            t.join(45)
            with _USO_TRAVA:
                dados = _USO["dados"]
    return dados


_FILA = ThreadPoolExecutor(max_workers=6)  # comandos independentes rodam ao mesmo tempo


def info_docker():
    if not docker_ligado():
        return {"ligado": False, "servico": servico_ativo("docker")}
    em_paralelo = {
        "imagens": _FILA.submit(rodar, ["docker", "images", "--format", "{{json .}}"]),
        "volumes": _FILA.submit(rodar, ["docker", "volume", "ls", "--format", "{{json .}}"]),
        "redes": _FILA.submit(rodar, ["docker", "network", "ls", "--format", "{{json .}}"]),
        "compose": _FILA.submit(rodar, ["docker", "compose", "ls", "-a", "--format", "json"]),
    }
    cont = json_linhas(rodar(["docker", "ps", "-a", "--no-trunc", "--format", "{{json .}}"])[1])
    ids = [c["ID"] for c in cont]
    limites = {}
    if ids:
        cod, txt = rodar(["docker", "inspect", "--format",
                          '{{json .Id}}\t{{json .HostConfig.Memory}}\t{{json .Config.Labels}}'] + ids, so_saida=True)
        for linha in txt.splitlines():
            try:
                cid, memoria, rotulos = (json.loads(x) for x in linha.split("\t"))
            except ValueError:
                continue
            rotulos = rotulos or {}
            limites[cid] = {"memoria": int(memoria or 0), "projeto": rotulos.get("com.docker.compose.project", ""),
                            "origem": rotulos.get("criado-por", "")}
    uso = uso_containers() if any(c.get("State") == "running" for c in cont) else {}
    containers = []
    for c in cont:
        cid = c["ID"]
        extra = limites.get(cid, {})
        containers.append({
            "id": cid[:12], "nome": c.get("Names", ""), "imagem": c.get("Image", ""), "estado": c.get("State", ""),
            "status": c.get("Status", ""), "portas": c.get("Ports", ""), "criado": c.get("RunningFor", ""),
            "limite_memoria": extra.get("memoria", 0), "projeto": extra.get("projeto", ""), "origem": extra.get("origem", ""),
            "cpu": uso.get(cid, {}).get("cpu", ""), "uso_memoria": uso.get(cid, {}).get("mem", ""),
        })
    imagens = [{"id": i.get("ID", ""), "nome": f'{i.get("Repository")}:{i.get("Tag")}', "tamanho": i.get("Size", ""),
                "criada": i.get("CreatedSince", "")}
               for i in json_linhas(em_paralelo["imagens"].result()[1])]
    volumes = [{"nome": v.get("Name", ""), "driver": v.get("Driver", "")}
               for v in json_linhas(em_paralelo["volumes"].result()[1])]
    redes = [{"nome": n.get("Name", ""), "driver": n.get("Driver", ""), "padrao": n.get("Name") in ("bridge", "host", "none")}
             for n in json_linhas(em_paralelo["redes"].result()[1])]
    projetos = []
    cod, txt = em_paralelo["compose"].result()
    if cod == 0 and txt.startswith("["):
        for p in json.loads(txt):
            projetos.append({"nome": p.get("Name", ""), "status": p.get("Status", ""), "arquivos": p.get("ConfigFiles", "")})
    return {"ligado": True, "servico": "active", "containers": containers, "imagens": imagens,
            "volumes": volumes, "projetos": projetos, "redes": redes,
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
        ok_ou_erro(rodar(["systemctl", "start", "docker.socket", "docker.service"], timeout=90))
        return "Docker ligado."
    if acao == "desligar":
        # o socket também, senão o Docker liga de novo no próximo uso
        ok_ou_erro(rodar(["systemctl", "stop", "docker.socket", "docker.service"], timeout=120))
        return "Docker desligado. Ele liga sozinho de novo quando você usar o docker ou clicar em Ligar."
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
    if acao == "sugestao":
        img = d.get("imagem", "").strip()
        if not REF_OK.match(img):
            raise Erro("Imagem inválida.")
        cod, txt = rodar(["docker", "image", "inspect", "-f", "{{json .Config.ExposedPorts}}", img], so_saida=True)
        expostas = sorted(int(p.split("/")[0]) for p in (json.loads(txt or "null") or {}) if p.split("/")[0].isdigit()) if cod == 0 else []
        usadas = {int(m) for m in re.findall(r":(\d+)->", rodar(["docker", "ps", "-a", "--format", "{{.Ports}}"], so_saida=True)[1])}
        usadas |= {8080, 8090}
        portas = []
        livre = 8100
        for p in expostas[:3]:
            while livre in usadas:
                livre += 1
            portas.append(f"{livre}:{p}")
            usadas.add(livre)
        nome = re.sub(r"[^a-z0-9_.-]", "-", img.split("/")[-1].split(":")[0].lower()) + "-1"
        while rodar(["docker", "inspect", nome])[0] == 0:
            nome = re.sub(r"-(\d+)$", lambda m: f"-{int(m.group(1)) + 1}", nome)
        return {"portas": ",".join(portas), "nome": nome}
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
    if acao == "rede_criar":
        nome = d.get("nome", "").strip()
        if not NOME_OK.match(nome):
            raise Erro("Nome de rede inválido.")
        ok_ou_erro(rodar(["docker", "network", "create", nome]))
        return f"Rede '{nome}' criada. Containers na mesma rede se encontram pelo nome."
    if acao == "rede_rm":
        nome = d.get("nome", "").strip()
        if not NOME_OK.match(nome):
            raise Erro("Rede inválida.")
        ok_ou_erro(rodar(["docker", "network", "rm", nome]))
        return f"Rede '{nome}' apagada."
    if acao == "exec":
        alvo, comando = d.get("container", ""), d.get("comando", "").strip()
        if not REF_OK.match(alvo) or not comando:
            raise Erro("Informe o container e o comando.")
        cod, txt = rodar(["docker", "exec", alvo, "sh", "-c", comando], timeout=120)
        return (txt or "(sem saída)") + ("" if cod == 0 else f"\n\n[terminou com código {cod}]")
    if acao == "inspecionar":
        alvo = d.get("container", "")
        if not REF_OK.match(alvo):
            raise Erro("Container inválido.")
        return ok_ou_erro(rodar(["docker", "inspect", alvo]))
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
            if orig.startswith(("~/", "/home/")):
                orig = str(dentro_da_home(orig))
            cmd += ["-v", f"{orig}:{dest}"]
        comando = d.get("comando", "").strip()
        if nome:
            if not NOME_OK.match(nome):
                raise Erro("Nome inválido: use letras, números, - _ .")
            cmd += ["--name", nome]
        for p in [x.strip() for x in d.get("portas", "").replace(";", ",").split(",") if x.strip()]:
            if not PORTAS_OK.match(p) or not all(1 <= int(n) <= 65535 for n in p.split("/")[0].split(":")):
                raise Erro(f"Porta inválida: {p} (use PC:CONTAINER, ex.: 8081:80; portas vão de 1 a 65535)")
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
        cpus = str(d.get("cpus", "")).strip()
        if cpus:
            if not re.fullmatch(r"\d{1,2}(\.\d{1,2})?", cpus):
                raise Erro("CPUs inválido (ex.: 0.5 ou 1).")
            cmd += ["--cpus", cpus]
        rede = d.get("rede", "").strip()
        if rede:
            if not NOME_OK.match(rede):
                raise Erro("Rede inválida.")
            cmd += ["--network", rede]
        if d.get("reiniciar"):
            cmd += ["--restart", "unless-stopped"]
        cmd.append(img)
        aviso = ""
        nome_img = img.split("/")[-1].split(":")[0].split("@")[0]
        if not comando and nome_img in IMAGENS_BASE:
            comando = "sleep infinity"
            aviso = (f"\nA imagem {nome_img} não tem um programa que fique rodando sozinho, então usei o comando "
                     "sleep infinity para o container continuar ligado. Use o Terminal dele para trabalhar.")
        if comando:
            import shlex
            try:
                cmd += shlex.split(comando)
            except ValueError:
                raise Erro("O comando tem aspas abertas e não fechadas. Confira as aspas do comando.") from None
        cod_run, saida = rodar(cmd, timeout=900)
        if cod_run != 0:
            raise Erro("\n".join(dicas_para(saida)) or saida)
        achado = re.findall(r"\b[0-9a-f]{64}\b", saida)  # o id (a saída também pode ter o download da imagem)
        cid = achado[-1][:12] if achado else nome
        time.sleep(2)
        estado = rodar(["docker", "inspect", "-f", "{{.State.Status}} {{.State.ExitCode}}", cid], so_saida=True)[1].split()
        if estado and estado[0] == "exited":
            logs = rodar(["docker", "logs", "--tail", "15", cid])[1]
            if estado[1:] == ["0"]:
                return (f"O container {nome or cid} rodou o programa dele e terminou com sucesso (programas de uma vez só, "
                        "como scripts, param quando acabam; servidores continuam ligados). Saída:\n" + logs[-1200:]).strip()
            raise Erro((f"O container {nome or cid} parou com erro (código {estado[1] if len(estado) > 1 else '?'}) logo depois de ligar. "
                        f"Veja a saída:\n{logs[-1200:]}\n" + "\n".join(dicas_para(logs))).strip())
        return f"Container {nome or cid} criado e rodando.{aviso}"
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
            texto = _texto_erro(e.read().decode("utf-8", "replace"))
            if e.code >= 500:
                m = re.search(r"Logging ID=([0-9a-f-]{36})", texto)
                causa = _causa_no_log(m.group(1) if m else "")
                raise ErroJenkins(e.code, f"O Jenkins teve um erro interno (código {e.code})" + (
                    f". Causa no log do Jenkins: {causa}" if causa else
                    ". Tente de novo em alguns segundos; se continuar, reinicie o Jenkins na aba Sistema."))
            if "already exists" in texto or "já existe" in texto.lower():
                raise ErroJenkins(e.code, "Já existe um item com esse nome no Jenkins. Escolha outro nome ou apague o antigo.")
            if e.code == 404:
                raise ErroJenkins(e.code, "Esse item não existe (mais) no Jenkins. A lista vai ser atualizada.")
            raise ErroJenkins(e.code, f"O Jenkins recusou o pedido (código {e.code}): {texto[:300]}")
        except (urllib.error.URLError, OSError) as e:
            raise Erro(f"Jenkins não respondeu ({e}).")


class ErroJenkins(Erro):
    def __init__(self, codigo, msg):
        super().__init__(msg)
        self.codigo = codigo


def _texto_erro(corpo):
    """Texto útil de uma página de erro do Jenkins (sem menu, busca, rodapé…)."""
    t = re.sub(r"(?is)<(script|style|head|header|footer|nav)\b[^>]*>.*?</\1>", " ", corpo)
    t = html_mod.unescape(re.sub(r"<[^>]+>", " ", t))
    for lixo in ("Skip to content", "Sign in", "log out", "REST API", "Dashboard", "Search"):
        t = t.replace(lixo, " ")
    t = re.sub(r"Jenkins\s+\d+\.\d+(\.\d+)?", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return re.sub(r"^(Jenkins( - Jenkins)?\s*)+", "", t).strip()


def _causa_no_log(logid):
    """Acha no log do Jenkins a exceção ligada ao "Logging ID" da página de erro
    (o aluno está no grupo systemd-journal, que pode ler o log)."""
    if not logid:
        return ""
    cod, txt = rodar(["journalctl", "-u", "jenkins", "--since", "-20min", "--no-pager", "-o", "cat"], timeout=20, so_saida=True)
    if cod != 0 or logid not in txt:
        return ""
    linhas = txt.splitlines()
    inicio = max(i for i, l in enumerate(linhas) if logid in l)
    causa = ""
    for l in linhas[inicio + 1:inicio + 80]:
        l = l.strip()
        if re.match(r"^\d{4}-\d{2}-\d{2} ", l):  # começou outra mensagem do log
            break
        m = re.match(r"^(Caused by: )?([\w.$]+(?:Exception|Error))(: .*)?$", l)
        if m:
            causa = (m.group(2).split(".")[-1] + (m.group(3) or ""))[:300]
    return causa


JEN = Jenkins()


def job_existe(nome):
    try:
        JEN.req(caminho_job(nome) + "/api/json?tree=name")
        return True
    except Erro:
        return False


def caminho_job(nome):
    if not nome or len(nome) > 200 or ".." in nome:
        raise Erro("Job inválido.")
    return "".join("/job/" + urllib.parse.quote(p, safe="") for p in nome.split("/"))


CAMPOS_BUILD = "number,result,timestamp,duration,building"
CAMPOS_JOB = (f"name,fullName,url,color,_class,buildable,description,inQueue,lastBuild[{CAMPOS_BUILD}],"
              f"builds[{CAMPOS_BUILD}]{{0,15}}")
NOMES_TIPO = {"WorkflowJob": "Pipeline", "FreeStyleProject": "Freestyle", "WorkflowMultiBranchProject": "Multibranch",
              "Folder": "Pasta", "OrganizationFolder": "Organização"}


def _job(j):
    lb = j.get("lastBuild") or {}
    classe = (j.get("_class") or "").split(".")[-1]
    return {"nome": j.get("fullName") or j.get("name"), "url": j.get("url"), "classe": classe,
            "tipo": NOMES_TIPO.get(classe, classe), "cor": j.get("color", ""),
            "desativado": (j.get("color") or "").startswith("disabled") or j.get("buildable") is False and classe in ("WorkflowJob", "FreeStyleProject"),
            "na_fila": j.get("inQueue", False), "descricao": j.get("description") or "",
            "ultimo": lb.get("number"), "resultado": "EM ANDAMENTO" if lb.get("building") else lb.get("result"),
            "quando": lb.get("timestamp"), "duracao": lb.get("duration"),
            "historico": [{"n": b.get("number"), "r": "EM ANDAMENTO" if b.get("building") else b.get("result"),
                           "t": b.get("timestamp"), "d": b.get("duration")} for b in (j.get("builds") or [])],
            "filhos": len(j.get("jobs") or [])}


def info_jenkins():
    servico = servico_ativo("jenkins")
    base = {"servico": servico, "url": JEN.url}
    if servico != "active":
        return {**base, "respondendo": False, "jobs": []}
    try:
        _, txt = JEN.req(f"/api/json?tree=jobs[{CAMPOS_JOB},jobs[{CAMPOS_JOB},jobs[{CAMPOS_JOB}]]]")
    except Erro as e:
        return {**base, "respondendo": False, "jobs": [], "erro": str(e)}
    jobs = []

    def andar(lista, nivel):
        for j in lista:
            item = _job(j)
            item["nivel"] = nivel
            jobs.append(item)
            andar(j.get("jobs") or [], nivel + 1)
    andar(json.loads(txt).get("jobs", []), 0)
    extra = {}
    try:
        c = json.loads(JEN.req("/computer/api/json?tree=busyExecutors,totalExecutors")[1])
        q = json.loads(JEN.req("/queue/api/json?tree=items[task[name],why,inQueueSince]")[1])
        extra = {"executores": c.get("totalExecutors", 0), "ocupados": c.get("busyExecutors", 0),
                 "fila": [{"job": i.get("task", {}).get("name"), "motivo": i.get("why")} for i in q.get("items", [])]}
    except Erro:
        pass
    return {**base, "respondendo": True, "jobs": jobs, **extra}


# ---------- montagem do config.xml de cada tipo de item
def _el(pai, tag, texto=None, **attrs):
    e = ET.SubElement(pai, tag, attrs)
    if texto is not None:
        e.text = str(texto)
    return e


def _git_scm(pai, url, branch, cred):
    scm = _el(pai, "scm", **{"class": "hudson.plugins.git.GitSCM", "plugin": "git"})
    _el(scm, "configVersion", 2)
    urc = _el(_el(scm, "userRemoteConfigs"), "hudson.plugins.git.UserRemoteConfig")
    _el(urc, "url", url)
    if cred:
        _el(urc, "credentialsId", cred)
    _el(_el(_el(scm, "branches"), "hudson.plugins.git.BranchSpec"), "name", f"*/{branch or 'main'}")
    _el(scm, "doGenerateSubmoduleConfigurations", "false")
    _el(scm, "submoduleCfg", **{"class": "empty-list"})
    _el(scm, "extensions")
    return scm


CRON_OK = re.compile(r"^[\w*/,\- #@]{1,100}\Z")


def _gatilhos(pai, d):
    trig = _el(pai, "triggers")
    for chave, classe in (("cron_scm", "hudson.triggers.SCMTrigger"), ("cron", "hudson.triggers.TimerTrigger")):
        spec = (d.get(chave) or "").strip()
        if spec:
            if not CRON_OK.match(spec):
                raise Erro(f"Horário inválido: {spec} (ex.: H/5 * * * *)")
            t = _el(trig, classe)
            _el(t, "spec", spec)
            if classe == "hudson.triggers.SCMTrigger":
                _el(t, "ignorePostCommitHooks", "false")
    return trig


def _url_git(url):
    url = (url or "").strip()
    if re.search(r"github\.com[/:]usuario/repositorio", url):
        raise Erro("Troque o endereço de exemplo (usuario/repositorio) pelo endereço do seu repositório no GitHub.")
    if not re.fullmatch(r"(https://|git@)[\w.@:/~\-]+?(\.git)?/?", url):
        raise Erro("URL do repositório inválida (ex.: https://github.com/usuario/repo.git ou git@github.com:usuario/repo.git).")
    return url


def xml_item(tipo, d):
    desc = d.get("descricao") or "Criado pelo Painel DevOps"
    cred = (d.get("credencial") or "").strip()
    if cred and not NOME_OK.match(cred):
        raise Erro("Credencial inválida.")
    if tipo == "pipeline" or tipo == "pipeline_scm":
        raiz = ET.Element("flow-definition", plugin="workflow-job")
        _el(raiz, "description", desc)
        _el(raiz, "keepDependencies", "false")
        props = _el(raiz, "properties")
        if d.get("cron") or d.get("cron_scm"):
            _gatilhos(_el(props, "org.jenkinsci.plugins.workflow.job.properties.PipelineTriggersJobProperty"), d)
        if tipo == "pipeline":
            df = _el(raiz, "definition", **{"class": "org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition", "plugin": "workflow-cps"})
            _el(df, "script", d.get("script") or SCRIPT_EXEMPLO)
            _el(df, "sandbox", "true")
        else:
            df = _el(raiz, "definition", **{"class": "org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition", "plugin": "workflow-cps"})
            _git_scm(df, _url_git(d.get("repo")), d.get("branch"), cred)
            _el(df, "scriptPath", d.get("jenkinsfile") or "Jenkinsfile")
            _el(df, "lightweight", "true")
        _el(raiz, "disabled", "false")
    elif tipo == "freestyle":
        raiz = ET.Element("project")
        _el(raiz, "description", desc)
        _el(raiz, "keepDependencies", "false")
        _el(raiz, "properties")
        if (d.get("repo") or "").strip():
            _git_scm(raiz, _url_git(d.get("repo")), d.get("branch"), cred)
        else:
            _el(raiz, "scm", **{"class": "hudson.scm.NullSCM"})
        _el(raiz, "canRoam", "true")
        _el(raiz, "disabled", "false")
        _el(raiz, "blockBuildWhenDownstreamBuilding", "false")
        _el(raiz, "blockBuildWhenUpstreamBuilding", "false")
        _gatilhos(raiz, d)
        _el(raiz, "concurrentBuild", "false")
        sh = _el(_el(raiz, "builders"), "hudson.tasks.Shell")
        _el(sh, "command", d.get("comandos") or 'echo "Ola do Jenkins (Freestyle)!"')
        _el(raiz, "publishers")
        _el(raiz, "buildWrappers")
    elif tipo == "multibranch":
        mb = "org.jenkinsci.plugins.workflow.multibranch.WorkflowMultiBranchProject"
        raiz = ET.Element(mb, plugin="workflow-multibranch")
        _el(raiz, "description", desc)
        _el(raiz, "properties")
        fv = _el(raiz, "folderViews", **{"class": "jenkins.branch.MultiBranchProjectViewHolder", "plugin": "branch-api"})
        _el(fv, "owner", **{"class": mb, "reference": "../.."})
        _el(raiz, "healthMetrics")
        ic = _el(raiz, "icon", **{"class": "jenkins.branch.MetadataActionFolderIcon", "plugin": "branch-api"})
        _el(ic, "owner", **{"class": mb, "reference": "../.."})
        orf = _el(raiz, "orphanedItemStrategy", **{"class": "com.cloudbees.hudson.plugins.folder.computed.DefaultOrphanedItemStrategy", "plugin": "cloudbees-folder"})
        for k, v in (("pruneDeadBranches", "true"), ("daysToKeep", "-1"), ("numToKeep", "-1"), ("abortBuilds", "false")):
            _el(orf, k, v)
        tr = _el(_el(raiz, "triggers"), "com.cloudbees.hudson.plugins.folder.computed.PeriodicFolderTrigger", plugin="cloudbees-folder")
        _el(tr, "spec", "H/15 * * * *")
        _el(tr, "interval", "900000")
        _el(raiz, "disabled", "false")
        fontes = _el(raiz, "sources", **{"class": "jenkins.branch.MultiBranchProject$BranchSourceList", "plugin": "branch-api"})
        bs = _el(_el(fontes, "data"), "jenkins.branch.BranchSource")
        src = _el(bs, "source", **{"class": "jenkins.plugins.git.GitSCMSource", "plugin": "git"})
        _el(src, "id", secrets.token_hex(8))
        _el(src, "remote", _url_git(d.get("repo")))
        if cred:
            _el(src, "credentialsId", cred)
        _el(_el(src, "traits"), "jenkins.plugins.git.traits.BranchDiscoveryTrait")
        st = _el(bs, "strategy", **{"class": "jenkins.branch.DefaultBranchPropertyStrategy"})
        _el(st, "properties", **{"class": "empty-list"})
        _el(fontes, "owner", **{"class": mb, "reference": "../.."})
        fac = _el(raiz, "factory", **{"class": "org.jenkinsci.plugins.workflow.multibranch.WorkflowBranchProjectFactory"})
        _el(fac, "owner", **{"class": mb, "reference": "../.."})
        _el(fac, "scriptPath", d.get("jenkinsfile") or "Jenkinsfile")
    elif tipo == "pasta":
        raiz = ET.Element("com.cloudbees.hudson.plugins.folder.Folder", plugin="cloudbees-folder")
        _el(raiz, "description", desc)
        _el(raiz, "properties")
        _el(raiz, "healthMetrics")
    else:
        raise Erro("Tipo de item desconhecido.")
    return b"<?xml version='1.1' encoding='UTF-8'?>\n" + ET.tostring(raiz)


MODELO_PIPELINE = None  # (compatibilidade)

SCRIPT_EXEMPLO = """pipeline {
  agent any
  stages {
    stage('Ola') {
      steps {
        echo 'Ola do Jenkins!'
      }
    }
  }
}
"""

CREDS = "/credentials/store/system/domain/_"


def info_credenciais():
    try:
        _, txt = JEN.req(CREDS + "/api/json?tree=credentials[id,displayName,typeName,description]")
    except Erro as e:
        return {"credenciais": [], "erro": str(e)}
    return {"credenciais": [{"id": c.get("id"), "nome": c.get("displayName"), "tipo": c.get("typeName"),
                             "descricao": c.get("description") or ""} for c in json.loads(txt).get("credentials", [])]}


def criar_credencial(d):
    tipo, cid = d.get("tipo"), (d.get("id") or "").strip()
    if not NOME_OK.match(cid):
        raise Erro("ID inválido: use letras, números, - _ . (ex.: github)")
    desc = d.get("descricao") or "Criada pelo Painel DevOps"
    if tipo == "usuario":
        if not (d.get("usuario") or "").strip() or not (d.get("senha") or "").strip():
            raise Erro("Preencha o usuário do GitHub e o token. Sem eles a credencial não funciona.")
        if not re.match(r"(ghp_|github_pat_|gho_|ghs_)", d.get("senha", "").strip()):
            raise Erro("Isso não parece um token do GitHub (eles começam com ghp_ ou github_pat_). "
                       "O GitHub não aceita a senha da conta: crie um token em github.com/settings/personal-access-tokens.")
        raiz = ET.Element("com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl")
        for k, v in (("scope", "GLOBAL"), ("id", cid), ("description", desc), ("username", d.get("usuario", "")),
                     ("password", d.get("senha", ""))):
            _el(raiz, k, v)
    elif tipo == "segredo":
        if not (d.get("segredo") or "").strip():
            raise Erro("Preencha o segredo.")
        raiz = ET.Element("org.jenkinsci.plugins.plaincredentials.impl.StringCredentialsImpl")
        for k, v in (("scope", "GLOBAL"), ("id", cid), ("description", desc), ("secret", d.get("segredo", ""))):
            _el(raiz, k, v)
    elif tipo == "ssh":
        chave = d.get("chave", "")
        if d.get("usar_minha_chave"):
            arq = HOME / ".ssh" / "id_ed25519"
            if not arq.is_file():
                raise Erro("Você ainda não tem chave SSH. Gere uma na aba Git.")
            chave = arq.read_text()
        if "PRIVATE KEY" not in chave:
            raise Erro("Cole a chave PRIVADA (começa com -----BEGIN OPENSSH PRIVATE KEY-----).")
        raiz = ET.Element("com.cloudbees.jenkins.plugins.sshcredentials.impl.BasicSSHUserPrivateKey")
        for k, v in (("scope", "GLOBAL"), ("id", cid), ("description", desc), ("username", d.get("usuario") or "git")):
            _el(raiz, k, v)
        pk = _el(raiz, "privateKeySource", **{"class": "com.cloudbees.jenkins.plugins.sshcredentials.impl.BasicSSHUserPrivateKey$DirectEntryPrivateKeySource"})
        _el(pk, "privateKey", chave)
    else:
        raise Erro("Tipo de credencial desconhecido.")
    if any(c["id"] == cid for c in info_credenciais().get("credenciais", [])):
        raise Erro(f"Já existe uma credencial com o ID {cid}. Use outro ID ou apague a antiga.")
    JEN.req(CREDS + "/createCredentials", ET.tostring(raiz), "application/xml")
    return f"Credencial '{cid}' criada. Use o ID '{cid}' nos jobs."


def acao_jenkins(d):
    acao = d.get("acao")
    if acao in ("ligar", "desligar"):
        ok_ou_erro(rodar(["systemctl", "start" if acao == "ligar" else "stop", "jenkins.service"], timeout=900))
        return "Jenkins ligado (pode levar 1 minuto para abrir)." if acao == "ligar" else "Jenkins desligado."
    if acao == "credenciais":
        return info_credenciais()
    if acao == "criar_credencial":
        return criar_credencial(d)
    if acao == "apagar_credencial":
        cid = d.get("id", "")
        if not NOME_OK.match(cid):
            raise Erro("Credencial inválida.")
        JEN.req(f"{CREDS}/credential/{urllib.parse.quote(cid, safe='')}/doDelete", b"")
        return f"Credencial '{cid}' apagada."
    nome = d.get("job", "").strip()
    if acao == "criar":
        tipo = d.get("tipo") or "pipeline"
        if not NOME_OK.match(nome):
            raise Erro("Nome inválido: use letras, números, - _ . (sem espaços)")
        destino = caminho_job(d["pasta"]) if d.get("pasta") else ""
        completo = f'{d["pasta"]}/{nome}' if d.get("pasta") else nome
        url, xml = f"{destino}/createItem?name=" + urllib.parse.quote(nome, safe=""), xml_item(tipo, d)
        try:
            JEN.req(url, xml, "application/xml")
        except ErroJenkins as e:
            # erro interno do Jenkins: às vezes o item é criado mesmo assim; senão, tenta mais uma vez
            if e.codigo < 500:
                raise
            time.sleep(2)
            if not job_existe(completo):
                time.sleep(3)
                JEN.req(url, xml, "application/xml")
        if tipo == "multibranch":
            JEN.req(caminho_job(completo) + "/build?delay=0sec", b"")
            return f"Multibranch '{completo}' criado. O Jenkins está procurando as branches com Jenkinsfile."
        return f"{ {'pipeline': 'Pipeline', 'pipeline_scm': 'Pipeline do Git', 'freestyle': 'Freestyle', 'pasta': 'Pasta'}[tipo] } '{completo}' criado."
    cj = caminho_job(nome)
    if acao == "parametros":
        _, txt = JEN.req(cj + "/api/json?tree=property[parameterDefinitions[name,type,description,choices,defaultParameterValue[value]]]")
        defs = []
        for prop in json.loads(txt).get("property", []):
            for p in prop.get("parameterDefinitions") or []:
                defs.append({"nome": p.get("name"), "tipo": (p.get("type") or "").replace("ParameterDefinition", ""),
                             "descricao": p.get("description") or "", "opcoes": p.get("choices") or [],
                             "padrao": (p.get("defaultParameterValue") or {}).get("value", "")})
        return {"parametros": defs}
    if acao == "construir":
        params = d.get("parametros")
        if isinstance(params, dict) and params:
            dados = urllib.parse.urlencode({str(k): str(v) for k, v in params.items()}).encode()
            JEN.req(cj + "/buildWithParameters?delay=0sec", dados, "application/x-www-form-urlencoded")
            return f"Construção de '{nome}' iniciada com os valores escolhidos."
        try:
            JEN.req(cj + "/build?delay=0sec", b"")
        except ErroJenkins as e:
            if e.codigo != 400:
                raise
            JEN.req(cj + "/buildWithParameters?delay=0sec", b"")
        return f"Construção de '{nome}' iniciada."
    if acao == "parar":
        JEN.req(cj + "/lastBuild/stop", b"")
        return "Pedido de parada enviado."
    if acao in ("ativar", "desativar"):
        JEN.req(cj + ("/enable" if acao == "ativar" else "/disable"), b"")
        return "Job ativado." if acao == "ativar" else "Job desativado (não roda até ser ativado)."
    if acao == "copiar":
        novo = d.get("novo", "").strip()
        if not NOME_OK.match(novo):
            raise Erro("Nome da cópia inválido.")
        pai = "/".join(nome.split("/")[:-1])
        # cria a cópia a partir do config.xml do original: o "copiar" do Jenkins deixa a cópia
        # travada ("not buildable") até alguém salvar a configuração pela tela
        _, cfg = JEN.req(cj + "/config.xml")
        JEN.req(f"{caminho_job(pai) if pai else ''}/createItem?name={urllib.parse.quote(novo, safe='')}",
                cfg.encode("utf-8"), "application/xml")
        return f"Cópia '{novo}' criada e pronta para construir."
    if acao == "console":
        n = str(d.get("numero") or "lastBuild")
        if n != "lastBuild" and not n.isdigit():
            raise Erro("Número de build inválido.")
        _, txt = JEN.req(f"{cj}/{n}/consoleText", timeout=30)
        txt = txt[-30000:]
        if re.search(r"Finished: (FAILURE|UNSTABLE)\s*$", txt):
            txt += "".join("\nDica: " + d for d in dicas_para(txt))
        return txt
    if acao == "etapas":
        try:
            _, txt = JEN.req(cj + "/lastBuild/wfapi/describe", timeout=20)
        except Erro:
            return {"etapas": []}
        dd = json.loads(txt)
        return {"numero": dd.get("id"), "status": dd.get("status"),
                "etapas": [{"nome": st.get("name"), "status": st.get("status"), "duracao": st.get("durationMillis", 0)}
                           for st in dd.get("stages", [])]}
    if acao == "ver_config":
        _, xml = JEN.req(cj + "/config.xml")
        raiz = ET.fromstring(xml)
        s = raiz.find("./definition/script")
        if s is not None:
            campo = "script"
            valor = s.text or ""
        elif raiz.find("./builders/hudson.tasks.Shell/command") is not None:
            campo = "comandos"
            valor = raiz.find("./builders/hudson.tasks.Shell/command").text or ""
        else:
            campo, valor = None, ""
        trig = raiz.find("./properties/org.jenkinsci.plugins.workflow.job.properties.PipelineTriggersJobProperty/triggers")
        if trig is None:
            trig = raiz.find("./triggers")
        cron = trig.find("./hudson.triggers.TimerTrigger/spec") if trig is not None else None
        scm = trig.find("./hudson.triggers.SCMTrigger/spec") if trig is not None else None
        repo = raiz.find(".//hudson.plugins.git.UserRemoteConfig/url")
        return {"campo": campo, "valor": valor, "cron": cron.text if cron is not None else "",
                "cron_scm": scm.text if scm is not None else "", "repo": repo.text if repo is not None else "",
                "gatilhos_ok": raiz.tag in ("flow-definition", "project")}
    if acao == "salvar_config":
        _, xml = JEN.req(cj + "/config.xml")
        raiz = ET.fromstring(xml)
        if "valor" in d:
            alvo = raiz.find("./definition/script")
            if alvo is None:
                alvo = raiz.find("./builders/hudson.tasks.Shell/command")
            if alvo is None:
                raise Erro("Este item não tem script/comandos editáveis aqui. Use 'Abrir' para editar no Jenkins.")
            alvo.text = d.get("valor", "")
        if "cron" in d or "cron_scm" in d:
            if raiz.tag == "flow-definition":
                props = raiz.find("./properties")
                if props is None:
                    props = _el(raiz, "properties")
                velho = props.find("./org.jenkinsci.plugins.workflow.job.properties.PipelineTriggersJobProperty")
                if velho is not None:
                    props.remove(velho)
                if d.get("cron") or d.get("cron_scm"):
                    _gatilhos(_el(props, "org.jenkinsci.plugins.workflow.job.properties.PipelineTriggersJobProperty"), d)
            elif raiz.tag == "project":
                velho = raiz.find("./triggers")
                pos = list(raiz).index(velho) if velho is not None else len(raiz)
                if velho is not None:
                    raiz.remove(velho)
                novo_t = _gatilhos(ET.Element("x"), d)
                raiz.insert(pos, novo_t)
        JEN.req(cj + "/config.xml", b"<?xml version='1.1' encoding='UTF-8'?>\n" + ET.tostring(raiz), "application/xml")
        return "Configuração salva."
    if acao == "apagar":
        JEN.req(cj + "/doDelete", b"")
        return f"'{nome}' apagado."
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
    branch = rodar(g + ["branch", "--show-current"], so_saida=True)[1] or "(sem branch)"
    status = rodar(g + ["status", "--porcelain=v1", "-b"], so_saida=True)[1].splitlines()
    cab = status[0] if status and status[0].startswith("##") else ""
    mudancas = [{"codigo": l[:2], "arquivo": l[3:]} for l in status if len(l) > 3 and l[2] == " " and not l.startswith("##")]
    log = []
    cod, txt = rodar(g + ["log", "-8", "--date=format:%d/%m %H:%M", "--pretty=format:%h\x1f%ad\x1f%an\x1f%s"], so_saida=True)
    if cod == 0:
        for l in txt.splitlines():
            p = l.split("\x1f")
            if len(p) == 4:
                log.append({"hash": p[0], "data": p[1], "autor": p[2], "msg": p[3]})
    branches = [b.strip() for b in rodar(g + ["branch", "--format=%(refname:short)"], so_saida=True)[1].splitlines() if b.strip()]
    remoto = rodar(g + ["remote", "get-url", "origin"], so_saida=True)[1] if rodar(g + ["remote"], so_saida=True)[1] else ""
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


CHAVE = HOME / ".ssh" / "id_ed25519"


def info_chave():
    pub = CHAVE.with_suffix(".pub")
    if not pub.is_file():
        return {"existe": False}
    return {"existe": True, "publica": pub.read_text().strip(), "arquivo": str(pub),
            "digital": rodar(["ssh-keygen", "-lf", str(pub)])[1]}


def info_git():
    nome = rodar(["git", "config", "--global", "user.name"])[1]
    email = rodar(["git", "config", "--global", "user.email"])[1]
    helper = rodar(["git", "config", "--global", "credential.helper"])[1]
    repos = repos_git()
    return {"usuario": nome, "email": email, "pasta_projetos": str(PROJETOS), "chave": info_chave(),
            "token_guardado": "cache" in helper and Path(HOME / ".cache/git/credential/socket").exists(),
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
    if acao == "gerar_chave":
        email = d.get("email", "").strip() or rodar(["git", "config", "--global", "user.email"])[1] or "aluno@devops-lab"
        if not re.fullmatch(r"[^@\s]+@[^@\s]+", email):
            raise Erro("E-mail inválido.")
        if CHAVE.exists() and not d.get("substituir"):
            raise Erro("Você já tem uma chave SSH. Marque 'substituir' para criar outra (a antiga deixa de funcionar).")
        CHAVE.parent.mkdir(mode=0o700, exist_ok=True)
        for f in (CHAVE, CHAVE.with_suffix(".pub")):
            f.unlink(missing_ok=True)
        ok_ou_erro(rodar(["ssh-keygen", "-t", "ed25519", "-C", email, "-f", str(CHAVE), "-N", "", "-q"]))
        return "Chave SSH criada. Agora copie a chave pública e cole no GitHub."
    if acao == "testar_github":
        cod, txt = rodar(["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
                          "-o", "ConnectTimeout=10", "git@github.com"], timeout=30)
        if "successfully authenticated" in txt:
            return "✔ Conectado ao GitHub: " + txt.splitlines()[-1]
        if "Permission denied" in txt:
            raise Erro("O GitHub recusou a chave. Confira se a chave pública foi colada em GitHub > Settings > SSH keys.")
        raise Erro("Não foi possível falar com o GitHub: " + txt[-300:])
    if acao == "salvar_token":
        usuario, token = d.get("usuario", "").strip(), d.get("token", "").strip()
        if not re.fullmatch(r"[A-Za-z0-9\-]{1,39}", usuario) or not re.fullmatch(r"[\w\-]{20,255}", token):
            raise Erro("Informe seu usuário do GitHub e um token válido (ghp_... ou github_pat_...).")
        try:
            horas = max(1, min(int(d.get("horas") or 8), 24))
        except (TypeError, ValueError):
            raise Erro("Informe as horas como um número de 1 a 24.") from None
        rodar(["git", "config", "--global", "credential.helper", f"cache --timeout={horas * 3600}"])
        ok_ou_erro(rodar(["git", "credential", "approve"],
                         entrada=f"protocol=https\nhost=github.com\nusername={usuario}\npassword={token}\n\n"))
        return f"Token guardado na memória por {horas} h (não fica salvo em arquivo). Push e pull por HTTPS já funcionam."
    if acao == "esquecer_token":
        rodar(["git", "credential-cache", "exit"])
        return "Token apagado da memória."
    repo = dentro_da_home(d.get("repo", ""))
    if not (repo / ".git").exists():
        raise Erro("Isto não é um repositório Git.")
    g = ["git", "-C", str(repo)]
    if acao == "remoto":
        url = d.get("url", "").strip()
        if not re.fullmatch(r"(https://|git@)[\w.@:/~\-]+?(\.git)?/?", url):
            raise Erro("URL inválida (ex.: https://github.com/usuario/repo.git ou git@github.com:usuario/repo.git).")
        tem = "origin" in rodar(g + ["remote"])[1].split()
        ok_ou_erro(rodar(g + (["remote", "set-url", "origin", url] if tem else ["remote", "add", "origin", url])))
        return f"Repositório remoto (origin) agora é {url}."
    if acao == "merge":
        b = d.get("branch", "").strip()
        if not BRANCH_OK.match(b):
            raise Erro("Branch inválida.")
        cod, txt = rodar(g + ["merge", "--no-edit", b])
        if cod != 0 and "CONFLICT" in txt:
            raise Erro("Conflito no merge! Abra no VS Code para resolver os arquivos marcados.\n" + txt[-800:])
        return ok_ou_erro((cod, txt)) or "Merge feito."
    if acao == "apagar_branch":
        b = d.get("branch", "").strip()
        if not BRANCH_OK.match(b):
            raise Erro("Branch inválida.")
        cod, txt = rodar(g + ["branch", "-D" if d.get("forcar") else "-d", b])
        if cod != 0 and "not fully merged" in txt:
            raise Erro(f"NAO_JUNTADA: A branch {b} tem commits que não foram juntados (merge) em outra branch. "
                       "Se apagar, esses commits se perdem.")
        ok_ou_erro((cod, txt))
        return f"Branch {b} apagada."
    if acao == "tag":
        t, msg = d.get("tag", "").strip(), d.get("mensagem", "").strip() or "versão"
        if not re.fullmatch(r"[\w.\-]{1,60}", t):
            raise Erro("Nome de tag inválido (ex.: v1.0.0).")
        ok_ou_erro(rodar(g + ["tag", "-a", t, "-m", msg]))
        return f"Tag {t} criada. Use Push para enviá-la ao GitHub."
    if acao == "stash":
        return ok_ou_erro(rodar(g + ["stash", "push", "-u", "-m", d.get("mensagem") or "guardado pelo painel"])) or "Mudanças guardadas."
    if acao == "stash_pop":
        return ok_ou_erro(rodar(g + ["stash", "pop"])) or "Mudanças devolvidas."
    if acao == "descartar":
        arq = d.get("arquivo", "")
        alvo = (repo / arq).resolve()
        if repo not in alvo.parents:
            raise Erro("Arquivo inválido.")
        if d.get("novo"):
            ok_ou_erro(rodar(g + ["clean", "-f", "--", arq]))
        else:
            ok_ou_erro(rodar(g + ["restore", "--staged", "--worktree", "--", arq]))
        return f"Mudanças em {arq} descartadas."
    if acao == "desfazer_commit":
        if rodar(g + ["rev-parse", "--verify", "-q", "HEAD~1"])[0] != 0:
            raise Erro("Este repositório só tem um commit: não existe commit anterior para voltar.")
        ok_ou_erro(rodar(g + ["reset", "--soft", "HEAD~1"]))
        return "Último commit desfeito (as mudanças continuam nos arquivos)."
    if acao == "grafico":
        return rodar(g + ["log", "--graph", "--oneline", "--decorate", "--all", "-60", "--date=short",
                          "--pretty=format:%h %d %s (%an, %ad)"])[1] or "(sem commits)"
    if acao == "info_repo":
        r = info_repo(str(repo))
        r["tags"] = rodar(g + ["tag", "--sort=-creatordate"])[1].splitlines()[:30]
        r["stashes"] = rodar(g + ["stash", "list"])[1].splitlines()
        return r
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
        cod_c, txt_c = rodar(g + ["commit", "-m", msg])
        if cod_c != 0:
            raise Erro("\n".join(dicas_para(txt_c)) or txt_c)
        return txt_c
    if acao in ("pull", "push"):
        cmd = g + (["pull", "--no-rebase", "--no-edit"] if acao == "pull" else ["push", "--follow-tags", "-u", "origin", "HEAD"])
        cod, txt = rodar(cmd, timeout=300)
        if cod != 0 and ("terminal prompts disabled" in txt or "could not read Username" in txt):
            raise Erro("O GitHub pediu login. Na aba Git, use 'Token do GitHub' (HTTPS) ou 'Chave SSH'.")
        return ok_ou_erro((cod, txt)) or "OK"
    if acao == "checkout":
        b = d.get("branch", "").strip()
        if not BRANCH_OK.match(b):
            raise Erro("Nome de branch inválido.")
        existe = b in [x.strip() for x in rodar(g + ["branch", "--format=%(refname:short)"])[1].splitlines()]
        return ok_ou_erro(rodar(g + (["switch", b] if existe else ["switch", "-c", b]))) or f"Agora na branch {b}."
    if acao == "diff":
        resumo_diff, diff = rodar(g + ["diff", "--stat"])[1], rodar(g + ["diff"])[1][:20000]
        return (resumo_diff + "\n\n" + diff) if (resumo_diff or diff) else "(sem diferenças)"
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
        if not re.match(r"^(http://(localhost|127\.0\.0\.1):\d+(/.*)?|https://github\.com/[\w./?=&\-]*)\Z", url):
            raise Erro("Endereço não permitido.")
        lancar(["firefox", url])
        return "Abrindo no navegador."
    caminho = dentro_da_home(d.get("caminho", str(PROJETOS)))
    if acao == "novo_arquivo":
        nome = d.get("nome", "").strip()
        if not re.fullmatch(r"[\w.\- ]{1,100}", nome) or not nome.strip(". "):
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
    portas = []
    for l in rodar(["ss", "-tlnH"])[1].splitlines():
        p = l.split()
        if len(p) >= 4:
            end = p[3]
            porta = end.rsplit(":", 1)[-1]
            if porta.isdigit() and int(porta) not in {p_["porta"] for p_ in portas}:
                portas.append({"porta": int(porta), "endereco": end, "so_local": end.startswith(("127.", "[::1]"))})
    conhecidas = {8080: "Jenkins", 8090: "Painel DevOps", 22: "SSH", 53: "DNS", 631: "Impressão"}
    for p_ in portas:
        p_["nome"] = conhecidas.get(p_["porta"], "")
    ip = rodar(["hostname", "-I"])[1].split()
    return {"mem_total": mem.get("MemTotal", 0), "mem_disponivel": mem.get("MemAvailable", 0),
            "swap_total": mem.get("SwapTotal", 0), "swap_livre": mem.get("SwapFree", 0),
            "disco_total": disco.total // 2**30, "disco_usado": (disco.total - disco.free) // 2**30,
            "carga": [round(x, 2) for x in carga], "cpus": os.cpu_count(), "processos": procs, "servicos": servicos,
            "portas": sorted(portas, key=lambda x: x["porta"]), "ip": ip}


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
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", PYTHONUNBUFFERED="1",
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
            if t["codigo"] not in (0, None, -15):
                for d in dicas_para("\n".join(t["linhas"][-300:])):
                    t["linhas"] += ["", "Dica: " + d]
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
    try:
        desde = max(0, int(q.get("desde", ["0"])[0]))
    except ValueError:
        desde = 0
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
        if a in ("compose_down_projeto", "compose_logs_projeto"):
            # projetos cujo arquivo não está na sua pasta (ex.: criados por um pipeline do Jenkins)
            proj = d.get("projeto", "").strip()
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", proj):
                raise Erro("Nome de projeto Compose inválido.")
            extra = ["down"] if a == "compose_down_projeto" else ["logs", "--tail", "200", "--no-color"]
            return iniciar_tarefa("docker", f"docker compose -p {proj} {extra[0]}", ["docker", "compose", "-p", proj] + extra)
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
        if a in ("pull", "push", "fetch"):
            cmd = {"pull": ["git", "pull", "--no-rebase", "--no-edit"], "fetch": ["git", "fetch", "--all", "--prune"],
                   "push": ["git", "push", "--follow-tags", "-u", "origin", "HEAD"]}[a]
            return iniciar_tarefa("git", f"git {a} ({repo.name})", cmd, cwd=str(repo))
        if a == "pull_juntar":
            branch = rodar(["git", "-C", str(repo), "branch", "--show-current"], so_saida=True)[1] or "main"
            return iniciar_tarefa("git", f"git pull juntando históricos ({repo.name})",
                                  ["git", "pull", "--no-rebase", "--no-edit", "--allow-unrelated-histories", "origin", branch], cwd=str(repo))
    if f == "vscode":
        if a not in ("instalar", "remover"):
            raise Erro("Ação do VS Code desconhecida.")
        ext = d.get("extensao", "").strip()
        if not re.fullmatch(r"[\w\-]+\.[\w.\-]+", ext):
            raise Erro("ID de extensão inválido (ex.: ms-python.python).")
        op = "--install-extension" if a == "instalar" else "--uninstall-extension"
        return iniciar_tarefa("vscode", f"{'instalar' if a == 'instalar' else 'remover'} extensão {ext}", ["code", op, ext])
    if f == "monitoramento":
        if a not in ("ligar", "desligar", "reiniciar"):
            raise Erro("Ação de monitoramento desconhecida.")
        if not MON_COMPOSE.is_file():
            raise Erro("O monitoramento não está instalado nesta VM.")
        if a == "ligar":
            # As imagens vêm na VM compactadas (imagens.tar.zst) para o .ova caber no limite do GitHub.
            # Na primeira vez o Docker carrega as imagens; depois liga em segundos.
            script = ('if [ -f imagens.tar.zst ] && ! docker compose config --images | xargs docker image inspect >/dev/null 2>&1; then '
                      'echo "== Primeira vez: preparando as imagens que vêm na VM (cerca de 1 minuto) =="; '
                      'zstd -d -q --long=27 -c imagens.tar.zst | docker load || exit 1; fi; '
                      'docker compose up -d')
            return iniciar_tarefa("monitoramento", "ligar o monitoramento", ["bash", "-c", script], cwd=str(MON_COMPOSE.parent))
        cmd = {"desligar": ["down"], "reiniciar": ["restart"]}[a]
        titulo = {"desligar": "desligar o monitoramento", "reiniciar": "reiniciar o monitoramento"}[a]
        return iniciar_tarefa("monitoramento", titulo, ["docker", "compose", "-f", str(MON_COMPOSE)] + cmd, cwd=str(MON_COMPOSE.parent))
    if f == "projeto" and a == "apagar":
        pasta = dentro_da_home(d.get("pasta", ""))
        if pasta.parent != PROJETOS or not pasta.is_dir():
            raise Erro("Só dá para apagar pastas de projeto que ficam direto em ~/projetos.")
        passos, nomes = [], []
        estado = pasta / "terraform.tfstate"
        if any(pasta.glob("*.tf")) and estado.is_file() and '"mode": "managed"' in estado.read_text(errors="replace"):
            passos.append("echo '== terraform destroy: apagando o que o projeto criou =='; terraform destroy -auto-approve -input=false -no-color")
            nomes.append("destroy")
        compose = next((c for c in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml") if (pasta / c).is_file()), None)
        if compose:
            passos.append(f"echo '== docker compose down: removendo containers e volumes do projeto =='; docker compose -f {compose} down -v --remove-orphans")
            nomes.append("compose down")
        passos.append('echo "== apagando a pasta $PWD =="; cd .. && rm -rf -- "$1" && echo "Projeto apagado."')
        return iniciar_tarefa("projeto", f"apagar projeto {pasta.name}" + (f" ({' + '.join(nomes)})" if nomes else ""),
                              ["bash", "-c", " && ".join(passos), "apagar", str(pasta)], cwd=str(pasta))
    if f == "terraform":
        pasta = dentro_da_home(d.get("pasta", ""))
        if not any(pasta.glob("*.tf")):
            raise Erro("Esta pasta não tem arquivos .tf.")
        cmds = {"init": ["init", "-input=false", "-no-color"], "validate": ["validate", "-no-color"],
                "plan": ["plan", "-input=false", "-no-color"], "apply": ["apply", "-auto-approve", "-input=false", "-no-color"],
                "destroy": ["destroy", "-auto-approve", "-input=false", "-no-color"], "fmt": ["fmt", "-diff", "-no-color"],
                "output": ["output", "-no-color"], "state": ["state", "list"], "show": ["show", "-no-color"],
                "graph": ["graph"], "refresh": ["apply", "-refresh-only", "-auto-approve", "-input=false", "-no-color"]}
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
        if a == "pytest":
            return iniciar_tarefa("python", f"pytest ({pasta.name})", [py, "-m", "pytest", "-v"], cwd=str(pasta))
        if a == "freeze":
            if not venv_py.exists():
                raise Erro("Crie o ambiente (.venv) primeiro.")
            return iniciar_tarefa("python", f"pip freeze > requirements.txt ({pasta.name})",
                                  ["sh", "-c", '"$1" -m pip freeze | tee requirements.txt', "freeze", py], cwd=str(pasta))
        if a == "piplist":
            return iniciar_tarefa("python", f"pip list ({pasta.name})", [py, "-m", "pip", "list"], cwd=str(pasta))
    raise Erro("Ação desconhecida.")


# ---------------------------------------------------------------- Terraform, Python, arquivos
def _pastas_projetos(prof_max=3):
    if not PROJETOS.is_dir():
        return
    for raiz, dirs, arqs in os.walk(PROJETOS):
        prof = len(Path(raiz).relative_to(PROJETOS).parts)
        dirs[:] = [x for x in dirs if not x.startswith(".") and x not in ("node_modules", "venv", ".venv", "__pycache__")
                   and prof < prof_max]
        yield Path(raiz), arqs


MON_COMPOSE = Path("/opt/devops-lab/monitoramento/docker-compose.yml")
MON_SERVICOS = [
    {"id": "grafana", "nome": "Grafana", "porta": 3000, "teste": "/api/health", "abrir": "/",
     "faz": "Gráficos e painéis. Já vem com o painel Esta VM (CPU, memória, disco, rede, containers).", "login": "aluno / devops"},
    {"id": "uptime-kuma", "nome": "Uptime Kuma", "porta": 3001, "teste": "/", "abrir": "/dashboard",
     "faz": "Vigia se os serviços estão no ar e mostra o histórico. Já vigia Jenkins, Painel, Grafana e Prometheus.", "login": "aluno / devops"},
    {"id": "prometheus", "nome": "Prometheus", "porta": 9090, "teste": "/-/ready", "abrir": "/targets",
     "faz": "Coleta as métricas a cada 15 s e guarda por 2 dias. É a fonte de dados do Grafana.", "login": ""},
    {"id": "node-exporter", "nome": "node-exporter", "porta": 9100, "teste": "/", "abrir": "/metrics",
     "faz": "Mede CPU, memória, disco e rede desta VM para o Prometheus.", "login": ""},
]


_SONDAS = ThreadPoolExecutor(max_workers=4)  # testa os 4 serviços ao mesmo tempo


def _no_ar(porta, caminho):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{porta}{caminho}", timeout=1.5) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except Exception:
        return False


def info_monitoramento():
    instalado = MON_COMPOSE.is_file()
    sondas = _SONDAS.map(lambda sv: _no_ar(sv["porta"], sv["teste"]), MON_SERVICOS)  # já começam a testar
    docker = servico_ativo("docker")
    estados = {}
    if instalado and docker == "active":
        for c in json_linhas(rodar(["docker", "compose", "-f", str(MON_COMPOSE), "ps", "-a", "--format", "json"], so_saida=True)[1]):
            estados[c.get("Service", "")] = c.get("State", "")
    servicos = []
    for sv, no_ar in zip(MON_SERVICOS, sondas, strict=True):
        servicos.append({**sv, "estado": estados.get(sv["id"], ""), "no_ar": no_ar,
                         "url": f"http://localhost:{sv['porta']}{sv['abrir']}"})
    return {"instalado": instalado, "docker": docker, "servicos": servicos,
            "arquivo": str(MON_COMPOSE)}


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
             ("Git", ["git", "--version"]), ("VS Code", ["code", "--version"]),
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
def _resumo_docker():
    dk = {"ligado": docker_ativo()}
    if dk["ligado"]:
        cont = json_linhas(rodar(["docker", "ps", "-a", "--format", "{{json .}}"])[1])
        estados = {}
        for c in cont:
            estados[c.get("State", "?")] = estados.get(c.get("State", "?"), 0) + 1
        dk.update(total=len(cont), rodando=estados.get("running", 0), estados=estados,
                  imagens=len(rodar(["docker", "images", "-q"])[1].split()))
    return dk


def _resumo_git():
    repos = repos_git()
    pend = sum(1 for r in repos if rodar(["git", "-C", r, "status", "--porcelain"])[1])
    return {"repos": len(repos), "com_mudancas": pend, "por_dia": commits_por_dia(repos)}


def resumo():
    # as partes não dependem uma da outra: rodam ao mesmo tempo (a Visão geral abre mais rápido)
    partes = {"jenkins": _FILA.submit(info_jenkins), "docker": _FILA.submit(_resumo_docker),
              "git": _FILA.submit(_resumo_git), "monitoramento": _FILA.submit(info_monitoramento)}
    s = info_sistema()
    j = partes["jenkins"].result()
    dk = partes["docker"].result()
    jobs = j.get("jobs", [])
    builds = []
    for x in jobs:
        for b in x.get("historico", []):
            builds.append({"job": x["nome"], **b})
    builds.sort(key=lambda b: b.get("t") or 0)
    return {"sistema": s, "docker": dk,
            "jenkins": {"servico": j["servico"], "respondendo": j.get("respondendo"), "jobs": len(jobs),
                        "falhas": sum(1 for x in jobs if x.get("resultado") == "FAILURE"),
                        "sucessos": sum(1 for x in jobs if x.get("resultado") == "SUCCESS")},
            "builds": builds[-30:], "historico": {k: HIST[k] for k in ("t", "cpu", "mem")},
            "git": partes["git"].result(),
            "vscode": {"recentes": len(vscode_recentes())},
            "monitoramento": (lambda m: {"ligados": sum(1 for x in m["servicos"] if x["no_ar"]), "total": len(m["servicos"])})(partes["monitoramento"].result()),
            "terraform": (lambda t: {"projetos": len(t["projetos"]), "recursos": sum(len(p["recursos"]) for p in t["projetos"])})(info_terraform()),
            "python": {"projetos": len(info_python()["projetos"])},
            "tarefas": listar_tarefas()["tarefas"][:12]}


def saude_lab():
    mem = {}
    for l in Path("/proc/meminfo").read_text().splitlines():
        k, v = l.split(":", 1)
        mem[k] = int(v.split()[0]) // 1024
    jenkins = servico_ativo("jenkins")
    respondendo = False
    if jenkins == "active":
        try:
            with urllib.request.urlopen(JEN.url + "/login", timeout=1.5) as r:
                respondendo = r.status == 200
        except Exception:
            respondendo = False
    return {"docker": servico_ativo("docker"), "jenkins": jenkins, "jenkins_respondendo": respondendo,
            "mem_total": mem.get("MemTotal", 0), "mem_disponivel": mem.get("MemAvailable", 0),
            "tarefas_rodando": sum(1 for t in listar_tarefas()["tarefas"] if not t.get("fim"))}


GETS = {"/api/saude-lab": saude_lab, "/api/resumo": resumo, "/api/docker": info_docker, "/api/jenkins": info_jenkins, "/api/git": info_git,
        "/api/vscode": info_vscode, "/api/sistema": info_sistema,
        "/api/compose-arquivos": lambda: {"arquivos": arquivos_compose()},
        "/api/modelo-pipeline": lambda: {"script": SCRIPT_EXEMPLO},
        "/api/historico": lambda: {k: HIST[k] for k in ("t", "cpu", "mem")},
        "/api/monitoramento": info_monitoramento, "/api/terraform": info_terraform, "/api/python": info_python,
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
            try:
                tam = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise Erro("Pedido inválido.") from None
            if tam < 0 or tam > 2_000_000:
                raise Erro("Dados grandes demais." if tam > 0 else "Pedido inválido.")
            try:
                dados = json.loads(self.rfile.read(tam) or b"{}")
            except ValueError:
                raise Erro("Os dados enviados não são JSON válido.") from None
            if not isinstance(dados, dict):
                raise Erro("Os dados enviados precisam ser um objeto JSON.")
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
