#!/usr/bin/env bash
# 02 - Interface gráfica leve: XFCE mínimo + LightDM com login automático
set -euxo pipefail

APT="apt-get -y -o DPkg::Lock::Timeout=900 -o APT::Install-Recommends=false -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"

$APT install \
  xserver-xorg-core xserver-xorg-input-libinput xserver-xorg-video-vmware xserver-xorg-video-fbdev \
  xfce4-session xfwm4 xfdesktop4 xfce4-panel xfce4-settings xfce4-terminal \
  xfce4-notifyd xfce4-whiskermenu-plugin thunar mousepad \
  lightdm lightdm-gtk-greeter dbus-x11 xdg-utils xdg-user-dirs \
  network-manager network-manager-gnome \
  adwaita-icon-theme elementary-xfce-icon-theme greybird-gtk-theme \
  fonts-dejavu-core fonts-liberation language-pack-pt-base locales

# Login automático no XFCE
mkdir -p /etc/lightdm/lightdm.conf.d
cat > /etc/lightdm/lightdm.conf.d/50-devops-lab.conf <<EOF
[Seat:*]
autologin-user=${LAB_USER}
autologin-user-timeout=0
user-session=xfce
greeter-session=lightdm-gtk-greeter
EOF
groupadd -f autologin
usermod -aG autologin "${LAB_USER}"

# Tema e ícones padrão
mkdir -p /etc/xdg/xfce4/xfconf/xfce-perchannel-xml
cat > /etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xsettings" version="1.0">
  <property name="Net" type="empty">
    <property name="ThemeName" type="string" value="Greybird"/>
    <property name="IconThemeName" type="string" value="elementary-xfce"/>
  </property>
</channel>
EOF

# Teclado ABNT2 também no ambiente gráfico
cat > /etc/default/keyboard <<'EOF'
XKBMODEL="abnt2"
XKBLAYOUT="br"
XKBVARIANT=""
XKBOPTIONS=""
BACKSPACE="guess"
EOF

systemctl set-default graphical.target

# Navegador (para o Jenkins em http://localhost:8080) - Firefox .deb oficial da Mozilla, sem snap
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://packages.mozilla.org/apt/repo-signing-key.gpg -o /etc/apt/keyrings/packages.mozilla.org.asc
echo "deb [signed-by=/etc/apt/keyrings/packages.mozilla.org.asc] https://packages.mozilla.org/apt mozilla main" \
  > /etc/apt/sources.list.d/mozilla.list
cat > /etc/apt/preferences.d/mozilla <<'EOF'
Package: *
Pin: origin packages.mozilla.org
Pin-Priority: 1000
EOF
$APT update
$APT install firefox firefox-l10n-pt-br || $APT install firefox || echo "AVISO: Firefox não instalado"
