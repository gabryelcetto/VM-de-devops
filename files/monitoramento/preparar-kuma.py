"""Prepara o Uptime Kuma na hora do build: cria a conta aluno/devops e os monitores
dos serviços do laboratório, para o aluno abrir e já ver tudo funcionando.
Usa a mesma API (socket.io) que a tela do Kuma usa.
Uso: python3 preparar-kuma.py [http://127.0.0.1:3001]
"""
import sys
import time

import socketio

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:3001"
USUARIO, SENHA = "aluno", "devops"
MONITORES = [
    ("Jenkins", "http://127.0.0.1:8080/login", "Jenkins do laboratório"),
    ("Painel DevOps", "http://127.0.0.1:8090/saude", "Painel DevOps (localhost:8090)"),
    ("Grafana", "http://127.0.0.1:3000/api/health", "Grafana do monitoramento"),
    ("Prometheus", "http://127.0.0.1:9090/-/ready", "Prometheus do monitoramento"),
]


def monitor(nome, url, descricao):
    # mesmos campos que a tela "Adicionar monitor" do Kuma envia
    return {
        "type": "http", "name": nome, "description": descricao, "parent": None, "url": url, "method": "GET",
        "interval": 60, "retryInterval": 60, "resendInterval": 0, "maxretries": 1,
        "notificationIDList": {}, "ignoreTls": False, "upsideDown": False, "expiryNotification": False,
        "maxredirects": 10, "accepted_statuscodes": ["200-299"], "dns_resolve_type": "A", "dns_resolve_server": "",
        "docker_container": "", "docker_host": None, "proxyId": None, "httpBodyEncoding": "json",
        "kafkaProducerBrokers": [], "kafkaProducerSaslOptions": {"mechanism": "None"}, "rabbitmqNodes": [],
        "conditions": [],
    }


existentes = []
sio = socketio.Client()


@sio.on("monitorList")
def _lista(dados):
    existentes[:] = [m.get("name") for m in (dados or {}).values()]


for tentativa in range(90):
    try:
        sio.connect(URL, transports=["websocket"], wait_timeout=10)
        break
    except Exception as e:  # o Kuma ainda está ligando
        print("esperando o Uptime Kuma…", e)
        time.sleep(2)
else:
    sys.exit("Uptime Kuma não respondeu")

r = sio.call("setup", (USUARIO, SENHA), timeout=60)
print("setup:", r)
r = sio.call("login", {"username": USUARIO, "password": SENHA, "token": ""}, timeout=60)
print("login:", {k: v for k, v in (r or {}).items() if k != "token"})
if not (r or {}).get("ok"):
    sys.exit("não consegui entrar no Uptime Kuma")
time.sleep(3)  # recebe a lista de monitores que já existem

for nome, url, desc in MONITORES:
    if nome in existentes:
        print("já existe:", nome)
        continue
    r = sio.call("add", monitor(nome, url, desc), timeout=60)
    print("monitor", nome, "->", r)
    if not (r or {}).get("ok"):
        sys.exit(f"falhou criar o monitor {nome}: {r}")

sio.disconnect()
print("Uptime Kuma pronto: aluno/devops com", len(MONITORES), "monitores")
