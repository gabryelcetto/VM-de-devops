#!/usr/bin/env bash
# Abre o Jenkins no navegador; se ele ainda estiver ligando, avisa e espera.
URL="http://localhost:8080"
pronto() { [ "$(curl -s -o /dev/null -w '%{http_code}' "$URL/login")" = "200" ]; }
if ! pronto; then
  notify-send -i applications-development "Jenkins" "Ligando o Jenkins... ele abre sozinho em até 2 minutos." 2>/dev/null || true
  for _ in $(seq 1 120); do pronto && break; sleep 2; done
fi
exec firefox "$URL"
