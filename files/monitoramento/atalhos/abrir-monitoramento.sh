#!/usr/bin/env bash
# Abre o Grafana, o Uptime Kuma ou o Prometheus no Firefox.
# Se o monitoramento estiver desligado, liga primeiro (na primeira vez prepara as imagens que vêm na VM).
# Uso: abrir-monitoramento grafana|kuma|prometheus
set -u
M=/opt/devops-lab/monitoramento
case "${1:-grafana}" in
  grafana)          NOME="Grafana";     URL="http://localhost:3000"; TESTE="http://127.0.0.1:3000/api/health" ;;
  kuma|uptime-kuma) NOME="Uptime Kuma"; URL="http://localhost:3001"; TESTE="http://127.0.0.1:3001/" ;;
  prometheus)       NOME="Prometheus";  URL="http://localhost:9090"; TESTE="http://127.0.0.1:9090/-/ready" ;;
  *) echo "uso: abrir-monitoramento grafana|kuma|prometheus" >&2; exit 2 ;;
esac

pronto() { local c; c="$(curl -s -o /dev/null -m 3 -w '%{http_code}' "$TESTE")"; [ "$c" -ge 200 ] && [ "$c" -lt 400 ]; }
avisa() { notify-send -i utilities-system-monitor "$NOME" "$1" 2>/dev/null || echo "$NOME: $1"; }
falhou() { avisa "$1 Abra o Painel DevOps, aba Monitoramento, para ver o motivo."; exit 1; }

if ! pronto; then
  cd "$M" || falhou "O monitoramento não está instalado nesta VM."
  avisa "Ligando o monitoramento (Grafana, Prometheus e Uptime Kuma)... na primeira vez leva cerca de 1 minuto."
  if [ -f imagens.tar.zst ] && ! docker compose config --images | xargs docker image inspect >/dev/null 2>&1; then
    zstd -d -q --long=27 -c imagens.tar.zst | docker load >/dev/null || falhou "Não consegui preparar as imagens."
  fi
  docker compose up -d >/dev/null 2>&1 || falhou "Não consegui ligar o monitoramento."
  for _ in $(seq 1 90); do pronto && break; sleep 2; done
  pronto || falhou "O $NOME está demorando para ligar."
fi
exec firefox "$URL"
