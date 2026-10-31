#!/usr/bin/env bash
# Abre o Portainer (painel completo do Docker). Usuário: admin  Senha: devops
# O container só roda quando é aberto, para não pesar no boot.
URL="http://localhost:9000"
pronto() { [ "$(curl -s -o /dev/null --max-time 2 -w '%{http_code}' "$URL/api/system/status")" = "200" ]; }
aviso() { notify-send -i devops-lab-docker "Docker (Portainer)" "$1" 2>/dev/null || true; }
if ! pronto; then
  aviso "Abrindo o painel do Docker... (usuário admin, senha devops)"
  if ! docker container inspect portainer >/dev/null 2>&1; then
    docker volume create portainer_data >/dev/null
    docker run -d --name portainer --restart=no -p 127.0.0.1:9000:9000 \
      -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data \
      portainer/portainer-ce:lts --http-enabled >/dev/null || { aviso "Não foi possível criar o Portainer."; exit 1; }
  else
    docker start portainer >/dev/null || { aviso "Não foi possível ligar o Portainer."; exit 1; }
  fi
  for _ in $(seq 1 60); do pronto && break; sleep 1; done
fi
exec firefox "$URL"
