#!/usr/bin/env bash
# Abre o Painel DevOps (liga o servidor local do painel se ainda não estiver rodando).
# Uso: painel-devops            -> liga e abre no Firefox
#      painel-devops --servidor -> só liga o servidor
URL="http://localhost:8090"
vivo() { curl -s -o /dev/null --max-time 2 "$URL/saude"; }
if ! vivo; then
  mkdir -p "$HOME/.cache"
  setsid -f python3 /usr/local/lib/devops-lab/painel/painel.py \
    > "$HOME/.cache/painel-devops.log" 2>&1 < /dev/null
  for _ in $(seq 1 50); do vivo && break; sleep 0.2; done
fi
[ "${1:-}" = "--servidor" ] && exit 0
exec firefox "$URL"
