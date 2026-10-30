#!/usr/bin/env bash
# 98 - Enxuga a VM: remove pacotes do Ubuntu Server/desktop que não servem aqui
#      (multipath, LVM, ModemManager, áudio, PackageKit, papéis de parede do Ubuntu...).
# Segurança: cada remoção é SIMULADA antes; se levar junto qualquer pacote protegido
# (interface, ferramentas DevOps, rede, boot...), aquele pacote é mantido.
set -uo pipefail

PROTEGIDOS="
apt dpkg bash coreutils sudo login passwd adduser systemd systemd-sysv systemd-resolved udev dbus
init grub-pc grub-common grub2-common netplan.io network-manager network-manager-gnome wpasupplicant
openssh-server curl ca-certificates locales language-pack-pt-base ubuntu-minimal
python3 python3-minimal python3.12 python3-pip python3-venv pipx git
code firefox firefox-l10n-pt-br jenkins openjdk-21-jre-headless terraform ansible-core
docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-buildx-plugin
lightdm lightdm-gtk-greeter xserver-xorg-core xserver-xorg-input-libinput
xfce4-session xfce4-panel xfwm4 xfdesktop4 xfce4-settings xfce4-terminal xfce4-notifyd
xfce4-whiskermenu-plugin xfce4-taskmanager xfce4-screenshooter xfce4-helpers exo-utils
thunar thunar-archive-plugin xarchiver mousepad gvfs librsvg2-common libnotify-bin
x11-xserver-utils xdg-user-dirs xdg-utils dbus-x11 libgtk-3-0t64 libgl1-mesa-dri
elementary-xfce-icon-theme greybird-gtk-theme adwaita-icon-theme fonts-ubuntu fonts-dejavu-core
virtualbox-guest-utils virtualbox-guest-x11 policykit-1 polkitd
"
protegido() {
  case "$1" in linux-image-*|linux-modules-*|linux-virtual) return 0 ;; esac
  for p in $PROTEGIDOS; do [ "$1" = "$p" ] && return 0; done
  return 1
}

# Protegidos instalados ficam "manuais": o autoremove nunca os leva
for p in $PROTEGIDOS; do
  dpkg -s "$p" >/dev/null 2>&1 && apt-mark manual "$p" >/dev/null
done

CANDIDATOS="
multipath-tools lvm2 mdadm open-iscsi bcache-tools btrfs-progs xfsprogs cryptsetup
packagekit modemmanager udisks2 ubuntu-drivers-common open-vm-tools fwupd
pipewire pipewire-bin pipewire-pulse wireplumber
ubuntu-wallpapers ubuntu-wallpapers-noble python3-botocore python3-boto3 libwebkitgtk-6.0-4
apport apport-symptoms pollinate ubuntu-release-upgrader-core update-notifier-common
cloud-init cloud-guest-utils landscape-common sosreport byobu lxd-installer ec2-instance-connect
"
REL=/usr/share/devops-lab/pacotes-removidos.txt
mkdir -p /usr/share/devops-lab
: > "$REL"
for c in $CANDIDATOS; do
  dpkg -s "$c" >/dev/null 2>&1 || continue
  LEVA="$(apt-get -s purge "$c" 2>/dev/null | awk '/^Purg /{print $2}')"
  BLOQ=""
  for p in $LEVA; do protegido "$p" && BLOQ="$BLOQ $p"; done
  if [ -n "$BLOQ" ]; then
    echo "MANTIDO  $c (levaria:$BLOQ)" | tee -a "$REL"
  else
    if apt-get -y purge "$c" >/dev/null 2>&1; then
      echo "REMOVIDO $c ($(echo "$LEVA" | wc -w) pacote(s): $(echo $LEVA))" | tee -a "$REL"
    else
      echo "ERRO     $c" | tee -a "$REL"
    fi
  fi
done

# autoremove também simulado: só roda se não levar nenhum protegido
LEVA="$(apt-get -s autoremove --purge 2>/dev/null | awk '/^Purg /{print $2}')"
BLOQ=""; for p in $LEVA; do protegido "$p" && BLOQ="$BLOQ $p"; done
if [ -z "$BLOQ" ]; then
  apt-get -y autoremove --purge >/dev/null && echo "AUTOREMOVE $(echo "$LEVA" | wc -w) pacote(s)" | tee -a "$REL"
else
  echo "AUTOREMOVE pulado (levaria:$BLOQ)" | tee -a "$REL"
fi

# Conferência: nada essencial pode ter sumido
set -e
for p in code firefox jenkins docker-ce terraform ansible-core git python3 lightdm xfce4-session xfce4-panel xfdesktop4 network-manager openssh-server; do
  dpkg -s "$p" >/dev/null
done
code --version >/dev/null 2>&1 || sudo -u "${LAB_USER}" code --version >/dev/null
docker --version && firefox --version && terraform -version >/dev/null && ansible --version >/dev/null
echo "Enxugamento concluído:"; cat "$REL"
