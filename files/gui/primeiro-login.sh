#!/usr/bin/env bash
# Roda a cada login do aluno (é rápido):
#  - marca os atalhos da Área de Trabalho como confiáveis (senão o XFCE pergunta antes de abrir)
#  - desliga o protetor de tela/apagamento automático do monitor
DESK="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
for f in "$DESK"/*.desktop; do
  [ -f "$f" ] || continue
  chmod +x "$f"
  gio set -t string "$f" metadata::xfce-exe-checksum "$(sha256sum "$f" | cut -d' ' -f1)" 2>/dev/null || true
done
xset s off -dpms 2>/dev/null || true
