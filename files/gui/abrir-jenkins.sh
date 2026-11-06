#!/usr/bin/env bash
# Abre o Jenkins no navegador. Ele fica desligado para a VM ficar leve: se estiver
# desligado, liga agora (sem senha, regra do polkit) e espera ele responder.
URL="http://localhost:8080"
pronto() { [ "$(curl -s -o /dev/null -w '%{http_code}' "$URL/login")" = "200" ]; }
if ! pronto; then
  systemctl is-active --quiet jenkins.service || systemctl start --no-block jenkins.service
  notify-send -i applications-development "Jenkins" "Ligando o Jenkins... ele abre sozinho em cerca de 1 minuto." 2>/dev/null || true
  # PC lento (VirtualBox com a tartaruga verde) pode levar alguns minutos
  for _ in $(seq 1 240); do pronto && break; sleep 2; done
fi
exec firefox "$URL"
