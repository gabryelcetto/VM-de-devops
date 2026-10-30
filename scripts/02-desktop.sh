#!/usr/bin/env bash
# 02 - Interface gráfica leve: XFCE mínimo + LightDM com login automático
set -euxo pipefail

APT="apt-get -y -o DPkg::Lock::Timeout=900 -o APT::Install-Recommends=false -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"

$APT install \
  xserver-xorg-core xserver-xorg-input-libinput xserver-xorg-video-fbdev \
  xfce4-session xfwm4 xfdesktop4 xfce4-panel xfce4-settings xfce4-terminal \
  xfce4-notifyd xfce4-whiskermenu-plugin thunar thunar-archive-plugin mousepad \
  xfce4-taskmanager xfce4-screenshooter xarchiver exo-utils xfce4-helpers \
  lightdm lightdm-gtk-greeter dbus-x11 xdg-utils xdg-user-dirs libnotify-bin \
  gvfs librsvg2-common x11-xserver-utils \
  network-manager network-manager-gnome \
  adwaita-icon-theme elementary-xfce-icon-theme greybird-gtk-theme \
  fonts-ubuntu fonts-dejavu-core fonts-liberation language-pack-pt-base locales

# Vídeo: usa sempre o driver "modesetting" do próprio Xorg.
# O driver "vmware" (xserver-xorg-video-vmware) deixava a janela do VirtualBox PRETA
# com a controladora VMSVGA (a VM funcionava por dentro, mas a imagem não chegava à tela).
apt-get -y purge xserver-xorg-video-vmware || true
install -d /etc/X11/xorg.conf.d
cat > /etc/X11/xorg.conf.d/10-devops-lab-video.conf <<'EOF'
# DevOps-Lab: driver de vídeo genérico (funciona com VBoxSVGA, VMSVGA e VBoxVGA)
Section "Device"
  Identifier "Placa de video"
  Driver "modesetting"
EndSection
EOF
test ! -e /usr/lib/xorg/modules/drivers/vmware_drv.so

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
$APT install firefox firefox-l10n-pt-br || $APT install firefox
