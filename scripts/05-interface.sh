#!/usr/bin/env bash
# 05 - Interface gráfica: papel de parede, painel, menu, tema, fontes, terminal,
#      atalhos na Área de Trabalho, Firefox (página inicial/favoritos) e tela de login.
set -euxo pipefail

G=/tmp/files/gui
HOME_DIR="$(getent passwd "${LAB_USER}" | cut -d: -f6)"
XFCONF_SYS=/etc/xdg/xfce4/xfconf/xfce-perchannel-xml

# ---------------------------------------------------------------- papel de parede
install -D -m 0644 "$G/devops-lab.svg" /usr/share/backgrounds/devops-lab.svg
# Vira o padrão do XFCE (xfdesktop 4.18 usa xfce-shapes.svg quando não há configuração)
if ! dpkg-divert --list /usr/share/backgrounds/xfce/xfce-shapes.svg | grep -q .; then
  dpkg-divert --local --rename \
    --divert /usr/share/backgrounds/xfce/xfce-shapes.svg.original \
    --add /usr/share/backgrounds/xfce/xfce-shapes.svg
fi
ln -sf /usr/share/backgrounds/devops-lab.svg /usr/share/backgrounds/xfce/xfce-shapes.svg

# ---------------------------------------------------------------- página inicial do Firefox
install -D -m 0644 "$G/inicio.html" /usr/share/devops-lab/inicio.html
install -D -m 0644 "$G/firefox-policies.json" /etc/firefox/policies/policies.json
python3 -m json.tool /etc/firefox/policies/policies.json >/dev/null

# ---------------------------------------------------------------- Jenkins no menu
install -m 0755 "$G/abrir-jenkins.sh" /usr/local/bin/abrir-jenkins
install -m 0644 "$G/jenkins-devops-lab.desktop" /usr/share/applications/jenkins-devops-lab.desktop

# ---------------------------------------------------------------- nome do atalho do VS Code
# (o pacote já usou "code.desktop"; versões novas podem usar outro nome)
find /usr/share/applications -maxdepth 1 \( -iname '*code*' -o -iname '*visual*' \) -print || true
CODE_FILE="$(grep -lE '^Exec=/usr/(share/code/code|bin/code)( |$)' /usr/share/applications/*.desktop 2>/dev/null | grep -v url-handler | head -n 1 || true)"
[ -n "$CODE_FILE" ] || CODE_FILE="$(grep -lE '^Name=Visual Studio Code$' /usr/share/applications/*.desktop | grep -v url-handler | head -n 1)"
CODE_ID="$(basename "$CODE_FILE")"
echo "Atalho do VS Code: $CODE_ID"
echo "$CODE_ID" > /usr/share/devops-lab/code-desktop-id
# troca "code.desktop" pelo nome real nos arquivos de configuração copiados
ajusta() { sed -i "s/\bcode\.desktop\b/${CODE_ID}/g" "$1"; }

# ---------------------------------------------------------------- padrões do XFCE (sistema e usuário)
# IMPORTANTE: não sobrescrever os arquivos de $XFCONF_SYS (o xfce4-session.xml de lá
# define a sessão "Failsafe"; sem ele o XFCE não abre). As nossas configurações vão
# só para o usuário (e /etc/skel) e se somam aos padrões do sistema.
test -s "$XFCONF_SYS/xfce4-session.xml"
install -m 0644 "$G/helpers.rc" /etc/xdg/xfce4/helpers.rc
install -m 0644 "$G/mimeapps.list" /etc/xdg/mimeapps.list; ajusta /etc/xdg/mimeapps.list

configura_usuario() {  # $1 = home de destino (aluno ou /etc/skel)
  local H="$1"
  install -d "$H/.config/xfce4/xfconf/xfce-perchannel-xml" "$H/.config/xfce4/terminal" "$H/.config/autostart"
  for f in "$G"/xfconf/*.xml; do
    install -m 0644 "$f" "$H/.config/xfce4/xfconf/xfce-perchannel-xml/$(basename "$f")"
    ajusta "$H/.config/xfce4/xfconf/xfce-perchannel-xml/$(basename "$f")"
  done
  install -m 0644 "$G/terminalrc" "$H/.config/xfce4/terminal/terminalrc"
  install -m 0644 "$G/helpers.rc" "$H/.config/xfce4/helpers.rc"
  install -m 0644 "$G/mimeapps.list" "$H/.config/mimeapps.list"; ajusta "$H/.config/mimeapps.list"
  # Atalhos do painel: cada lançador tem sua pasta com o .desktop
  local id app
  for pair in 3:thunar.desktop 4:xfce4-terminal.desktop 5:firefox.desktop "6:${CODE_ID}" 7:jenkins-devops-lab.desktop; do
    id="${pair%%:*}"; app="${pair#*:}"
    install -d "$H/.config/xfce4/panel/launcher-$id"
    install -m 0644 "/usr/share/applications/$app" "$H/.config/xfce4/panel/launcher-$id/$app"
  done
  # Menu Whisker (formato antigo, caso a versão não leia o xfconf)
  cat > "$H/.config/xfce4/panel/whiskermenu-1.rc" <<'RC'
favorites=xfce4-terminal.desktop,code.desktop,firefox.desktop,jenkins-devops-lab.desktop,thunar.desktop,org.xfce.mousepad.desktop,xfce4-taskmanager.desktop,xfce4-screenshooter.desktop
button-title=Aplicativos
show-button-title=true
show-button-icon=true
RC
  ajusta "$H/.config/xfce4/panel/whiskermenu-1.rc"
}
configura_usuario /etc/skel
configura_usuario "$HOME_DIR"

# ---------------------------------------------------------------- ajustes a cada login
install -m 0755 "$G/primeiro-login.sh" /usr/local/bin/devops-lab-login
install -m 0644 "$G/primeiro-login.desktop" /etc/xdg/autostart/devops-lab-login.desktop
# Acessibilidade (at-spi) atrasa o login e não é usada aqui
if [ -f /etc/xdg/autostart/at-spi-dbus-bus.desktop ]; then
  printf '[Desktop Entry]\nHidden=true\n' > "$HOME_DIR/.config/autostart/at-spi-dbus-bus.desktop"
fi

# ---------------------------------------------------------------- prompt com a branch do git
cat >> "$HOME_DIR/.bashrc" <<'BASHRC'

# DevOps-Lab: mostra a branch do git no prompt
if [ -f /usr/lib/git-core/git-sh-prompt ]; then
  . /usr/lib/git-core/git-sh-prompt
  PS1='\[\e[1;32m\]\u@\h\[\e[0m\]:\[\e[1;34m\]\w\[\e[0;33m\]$(__git_ps1 " (%s)")\[\e[0m\]\$ '
fi
BASHRC

# ---------------------------------------------------------------- tela de login (LightDM)
install -D -m 0644 "$G/lightdm-gtk-greeter.conf" /etc/lightdm/lightdm-gtk-greeter.conf.d/50-devops-lab.conf

chown -R "${LAB_USER}:${LAB_USER}" "$HOME_DIR"

# ---------------------------------------------------------------- conferências
test -s /usr/share/backgrounds/xfce/xfce-shapes.svg
fc-list > /tmp/fontes.txt
grep -qi "Ubuntu Mono" /tmp/fontes.txt
for app in thunar.desktop xfce4-terminal.desktop firefox.desktop "$CODE_ID" jenkins-devops-lab.desktop org.xfce.mousepad.desktop xfce4-taskmanager.desktop xfce4-screenshooter.desktop; do
  test -f "/usr/share/applications/$app" || { echo "falta $app"; exit 1; }
done
grep -q "$CODE_ID" "$HOME_DIR/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml"
for f in "$HOME_DIR"/.config/xfce4/xfconf/xfce-perchannel-xml/*.xml; do
  python3 -c "import sys, xml.dom.minidom; xml.dom.minidom.parse(sys.argv[1])" "$f"
done
