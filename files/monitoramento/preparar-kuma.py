"""Prepara o Uptime Kuma na hora do build: cria a conta aluno/devops e os monitores
dos serviços do laboratório, para o aluno abrir e já ver tudo funcionando.
Usa a mesma API (socket.io) que a tela do Kuma usa.

Uso:
  python3 preparar-kuma.py contas [http://127.0.0.1:3001]   (Kuma ligado)
  python3 preparar-kuma.py senha /caminho/kuma.db             (Kuma DESLIGADO)
  python3 preparar-kuma.py testar [http://127.0.0.1:3001]   (confere aluno/devops e monitores)

Por que dois passos: o Kuma recusa senhas fracas na criação da conta ("devops" é fraca
para ele). Então a conta nasce com uma senha temporária forte e, com o Kuma desligado,
a senha vira "devops" direto no banco (mesmo formato bcrypt que o Kuma usa), igual ao
resto do laboratório.
"""
import sys
import time

USUARIO, SENHA, SENHA_TEMP = "aluno", "devops", "Lab-DevOps-2026-temporaria"
MONITORES = [
    ("Jenkins", "http://127.0.0.1:8080/login", "Jenkins do laboratório"),
    ("Painel DevOps", "http://127.0.0.1:8090/saude", "Painel DevOps (localhost:8090)"),
    ("Grafana", "http://127.0.0.1:3000/api/health", "Grafana do monitoramento"),
    ("Prometheus", "http://127.0.0.1:9090/-/ready", "Prometheus do monitoramento"),
]


def monitor(nome, url, descricao):
    # mesmos campos (e valores padrão) que a tela "Adicionar monitor" do Kuma envia
    return {
        "type": "http", "name": nome, "description": descricao, "parent": None, "url": url, "method": "GET",
        "interval": 60, "retryInterval": 60, "resendInterval": 0, "maxretries": 1,
        "notificationIDList": {}, "ignoreTls": False, "upsideDown": False, "expiryNotification": False,
        "maxredirects": 10, "accepted_statuscodes": ["200-299"], "dns_resolve_type": "A", "dns_resolve_server": "",
        "docker_container": "", "docker_host": None, "proxyId": None, "httpBodyEncoding": "json",
        "kafkaProducerBrokers": [], "kafkaProducerSaslOptions": {"mechanism": "None"}, "rabbitmqNodes": [],
        "conditions": [],
    }


def conectar(url, existentes):
    import socketio

    sio = socketio.Client()

    @sio.on("monitorList")
    def _lista(dados):
        existentes[:] = [m.get("name") for m in (dados or {}).values()]

    for _ in range(90):
        try:
            sio.connect(url, transports=["websocket"], wait_timeout=10)
            break
        except Exception as e:  # o Kuma ainda está ligando
            print("esperando o Uptime Kuma…", e)
            time.sleep(2)
    else:
        sys.exit("Uptime Kuma não respondeu")

    # O Kuma só registra os comandos depois de terminar umas consultas ao banco, logo após
    # a conexão; um comando que chega antes disso se perde. Pergunta até ele responder.
    precisa = None
    for _ in range(30):
        try:
            precisa = sio.call("needSetup", timeout=5)
            break
        except Exception:
            print("esperando o Uptime Kuma aceitar comandos…")
    else:
        sys.exit("Uptime Kuma não respondeu aos comandos")
    return sio, precisa


def contas(url):
    existentes = []
    sio, precisa = conectar(url, existentes)
    print("precisa criar a conta:", precisa)
    if precisa:
        r = sio.call("setup", (USUARIO, SENHA_TEMP), timeout=60)
        print("setup:", r)
        if not (r or {}).get("ok"):
            sys.exit(f"não consegui criar a conta: {r}")

    r = None
    for senha in (SENHA_TEMP, SENHA):
        r = sio.call("login", {"username": USUARIO, "password": senha, "token": ""}, timeout=60)
        if (r or {}).get("ok"):
            break
    print("login:", {k: v for k, v in (r or {}).items() if k != "token"})
    if not (r or {}).get("ok"):
        sys.exit("não consegui entrar no Uptime Kuma")
    time.sleep(3)  # recebe a lista de monitores que já existem

    for nome, endereco, desc in MONITORES:
        if nome in existentes:
            print("já existe:", nome)
            continue
        r = sio.call("add", monitor(nome, endereco, desc), timeout=60)
        print("monitor", nome, "->", r)
        if not (r or {}).get("ok"):
            sys.exit(f"falhou criar o monitor {nome}: {r}")

    sio.disconnect()
    print("Uptime Kuma pronto:", len(MONITORES), "monitores")


def testar(url):
    existentes = []
    sio, _ = conectar(url, existentes)
    r = sio.call("login", {"username": USUARIO, "password": SENHA, "token": ""}, timeout=60)
    if not (r or {}).get("ok"):
        sys.exit(f"login {USUARIO}/{SENHA} recusado: {r}")
    time.sleep(3)
    faltam = [n for n, _, _ in MONITORES if n not in existentes]
    sio.disconnect()
    if faltam:
        sys.exit(f"monitores faltando: {faltam}")
    print(f"login {USUARIO}/{SENHA} OK; monitores: {existentes}")


def senha(banco):
    import sqlite3

    import bcrypt

    h = bcrypt.hashpw(SENHA.encode(), bcrypt.gensalt(rounds=10, prefix=b"2a")).decode()
    con = sqlite3.connect(banco)
    n = con.execute("UPDATE user SET password = ? WHERE username = ?", (h, USUARIO)).rowcount
    # apaga o histórico do build (Jenkins e Painel aparecem "fora" enquanto a VM é montada):
    # o aluno começa com o histórico limpo
    tabelas = {t for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    for t in ("heartbeat", "stat_minutely", "stat_hourly", "stat_daily"):
        if t in tabelas:
            con.execute(f"DELETE FROM {t}")
    con.commit()
    con.execute("VACUUM")
    con.close()
    if n != 1:
        sys.exit(f"conta {USUARIO} não encontrada em {banco}")
    print(f"senha do Uptime Kuma: {USUARIO}/{SENHA}")


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "contas"
    if modo == "senha":
        senha(sys.argv[2])
    elif modo == "testar":
        testar(sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:3001")
    else:
        contas(sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:3001")
