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

# Se a VM estiver com a controladora VMSVGA (ex.: arquivo compatível com VirtualBox 6.1),
# o Linux começa numa resolução enorme (1920x1440). Ajusta para 1280x800.
if grep -q '^vmwgfx ' /proc/modules 2>/dev/null; then
  SAIDA="$(xrandr 2>/dev/null | awk '/ connected/{print $1; exit}')"
  LARG="$(xrandr 2>/dev/null | sed -n 's/.*current \([0-9]*\) x.*/\1/p')"
  if [ -n "$SAIDA" ] && [ "${LARG:-0}" -gt 1600 ]; then
    xrandr --output "$SAIDA" --mode 1280x800 2>/dev/null || xrandr --output "$SAIDA" --mode 1024x768 2>/dev/null || true
  fi
fi
