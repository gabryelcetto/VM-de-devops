#!/usr/bin/env bash
# 08 - Monitoramento: Grafana + Prometheus + node-exporter + Uptime Kuma (Docker Compose).
#      As imagens já vêm baixadas; tudo fica DESLIGADO até o aluno ligar pelo Painel DevOps
#      (aba Monitoramento), para não gastar memória à toa.
#      Grafana já vem com a fonte de dados Prometheus e o painel "Esta VM";
#      Uptime Kuma já vem com a conta aluno/devops e monitores dos serviços do laboratório.
set -euxo pipefail

M=/opt/devops-lab/monitoramento
install -d "$M"
cp -r /tmp/files/monitoramento/. "$M/"
rm -f "$M/preparar-kuma.py"
chmod -R a+rX "$M"

systemctl start docker
cd "$M"
for t in 1 2 3; do docker compose pull -q && break; echo "falhou baixar as imagens (tentativa $t)"; sleep 20; done
docker compose up -d

espera() {  # espera um endereço responder
  for _ in $(seq 1 90); do curl -fsS -o /dev/null "$1" && return 0; sleep 2; done
  echo "ERRO: não respondeu: $1"; docker compose ps; docker compose logs --tail 40; return 1
}
espera http://127.0.0.1:9090/-/ready
espera http://127.0.0.1:9100/metrics
espera http://127.0.0.1:3000/api/health
espera http://127.0.0.1:3001/

# Prometheus coletando esta VM, o Docker e ele mesmo
ok=0
for _ in $(seq 1 30); do
  if curl -fsS 'http://127.0.0.1:9090/api/v1/query?query=up' | python3 -c '
import json, sys
r = json.load(sys.stdin)["data"]["result"]
s = {x["labels"]["job"]: x["value"][1] for x in r}
print(s)
sys.exit(0 if all(s.get(j) == "1" for j in ("prometheus", "esta-vm", "docker")) else 1)'; then ok=1; break; fi
  sleep 3
done
[ "$ok" = 1 ]

# Grafana: fonte de dados funcionando e painel "Esta VM" instalado
curl -fsS -u aluno:devops http://127.0.0.1:3000/api/datasources/uid/prometheus/health | tee /dev/stderr | grep -qi '"status":"OK"'
curl -fsS -u aluno:devops http://127.0.0.1:3000/api/dashboards/uid/esta-vm | grep -q 'Esta VM'

# Uptime Kuma: conta e monitores (pela mesma API que a tela usa; ferramenta temporária)
python3 -m venv /tmp/kseed
/tmp/kseed/bin/pip install -q "python-socketio[client]" websocket-client
/tmp/kseed/bin/python /tmp/files/monitoramento/preparar-kuma.py http://127.0.0.1:3001
rm -rf /tmp/kseed

# Desliga (os containers saem; imagens e dados ficam nos volumes)
docker compose down
docker image ls
docker volume ls
