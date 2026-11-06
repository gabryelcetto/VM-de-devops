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
rm -rf "$M/preparar-kuma.py" "$M/atalhos"
chmod -R a+rX "$M"

# Atalhos (menu e área de trabalho): abrem o serviço e ligam o monitoramento se estiver desligado
A=/tmp/files/monitoramento/atalhos
install -m 0755 "$A/abrir-monitoramento.sh" /usr/local/bin/abrir-monitoramento
for app in grafana uptime-kuma prometheus; do
  install -m 0644 "$A/$app-devops-lab.desktop" "/usr/share/applications/$app-devops-lab.desktop"
done
for i in grafana uptime prometheus; do
  install -D -m 0644 "$A/icone-$i.svg" "/usr/share/icons/hicolor/scalable/apps/devops-lab-$i.svg"
done
gtk-update-icon-cache -f -q /usr/share/icons/hicolor || true
HOME_DIR="$(getent passwd "${LAB_USER}" | cut -d: -f6)"
DESKTOP="$(sudo -u "${LAB_USER}" -H xdg-user-dir DESKTOP 2>/dev/null || true)"
if [ -z "${DESKTOP}" ] || [ "${DESKTOP}" = "${HOME_DIR}" ]; then DESKTOP="${HOME_DIR}/Área de Trabalho"; fi
install -d -o "${LAB_USER}" -g "${LAB_USER}" "${DESKTOP}"
for app in grafana uptime-kuma; do
  install -m 0755 -o "${LAB_USER}" -g "${LAB_USER}" "/usr/share/applications/$app-devops-lab.desktop" "${DESKTOP}/$app-devops-lab.desktop"
done

systemctl start docker
cd "$M"
for t in 1 2 3; do docker compose pull -q && break; echo "falhou baixar as imagens (tentativa $t)"; sleep 20; done
docker compose up -d

diagnostico() {  # o que aconteceu com os containers (para entender falhas no build)
  set +e
  docker compose ps -a
  for c in $(docker compose ps -aq); do
    docker inspect -f '{{.Name}} estado={{.State.Status}} saida={{.State.ExitCode}} oom={{.State.OOMKilled}} erro={{.State.Error}} inicio={{.State.StartedAt}} fim={{.State.FinishedAt}}' "$c"
  done
  free -m; uptime
  journalctl -k --since "-10 min" --no-pager | tail -n 40
  journalctl -u docker -u containerd -u earlyoom --since "-10 min" --no-pager | tail -n 80
  ps -eo pid,rss,etimes,comm --sort=-rss | head -n 15
  set -e
}
espera() {  # espera um endereço responder; se os containers caírem, mostra o motivo e sobe de novo uma vez
  local tentou=0
  for _ in $(seq 1 120); do
    curl -fsS -o /dev/null "$1" && return 0
    if [ "$tentou" = 0 ] && [ -n "$(docker compose ps -aq --status exited)" ]; then
      echo "AVISO: containers do monitoramento pararam sozinhos:"; diagnostico
      tentou=1; docker compose up -d
    fi
    sleep 2
  done
  echo "ERRO: não respondeu: $1"; diagnostico; docker compose logs --tail 40; return 1
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
s = {x["metric"]["job"]: x["value"][1] for x in r}
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
/tmp/kseed/bin/pip install -q "python-socketio[client]" websocket-client bcrypt
K=/tmp/files/monitoramento/preparar-kuma.py
/tmp/kseed/bin/python "$K" contas http://127.0.0.1:3001

# Desliga (os containers saem; imagens e dados ficam nos volumes)
docker compose down

# Senha aluno/devops (o Kuma não aceita senha fraca pela tela; vai direto no banco)
KDB="$(docker volume inspect -f '{{.Mountpoint}}' monitoramento_kuma-dados)/kuma.db"
/tmp/kseed/bin/python "$K" senha "$KDB"

# Confere: liga só o Kuma, entra com aluno/devops e vê os monitores
docker compose up -d uptime-kuma
espera http://127.0.0.1:3001/
/tmp/kseed/bin/python "$K" testar http://127.0.0.1:3001
docker compose down
# de novo com o Kuma desligado: limpa o histórico gerado durante o build
/tmp/kseed/bin/python "$K" senha "$KDB"
rm -rf /tmp/kseed

# Imagens guardadas compactadas com zstd (bem menor que a compressão do .ova): o .ova cabe no
# limite de 2 GiB do GitHub. O Painel carrega as imagens na primeira vez que o aluno liga.
apt-get -y -o DPkg::Lock::Timeout=900 install zstd
IMGS="$(docker compose config --images | sort -u | tr '\n' ' ')"
echo "Guardando: $IMGS"
docker save $IMGS | zstd -19 --long=27 -T0 -q -o "$M/imagens.tar.zst"
zstd -tq --long=27 "$M/imagens.tar.zst"
chmod 644 "$M/imagens.tar.zst"
ls -la "$M/imagens.tar.zst"
docker rmi $IMGS
docker image ls
docker volume ls
