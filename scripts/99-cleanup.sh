#!/usr/bin/env bash
# 99 - Limpeza para deixar o .ova o menor possível
set -euxo pipefail

apt-get -y purge intel-microcode amd64-microcode || true
apt-get -y autoremove --purge
# kernels antigos: mantém o que está rodando e o mais novo instalado
RUNNING="$(uname -r)"
NEWEST="$(find /boot -maxdepth 1 -name 'vmlinuz-*' -printf '%f\n' | sed 's/^vmlinuz-//' | sort -V | tail -n 1)"
dpkg -l 'linux-image-[0-9]*' 'linux-modules-[0-9]*' 'linux-modules-extra-[0-9]*' 2>/dev/null \
  | awk '/^ii/{print $2}' | grep -v -- "${RUNNING}" | grep -v -- "${NEWEST:-none}" \
  | xargs -r apt-get -y purge || true
apt-get -y clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* /var/cache/apt/*.bin /var/cache/man/* /var/cache/fontconfig/* /root/.cache "/home/${LAB_USER}/.cache"
rm -rf /usr/share/doc/*/changelog* /usr/share/man/??_* /var/lib/docker/tmp/*
# Jenkins: tira cache do instalador de plugins e as cópias "descompactadas" dos plugins
# (o Jenkins recria no primeiro boot; economiza ~100 MB no .ova)
systemctl stop jenkins || true
rm -rf /var/lib/jenkins/.cache /var/lib/jenkins/logs/* /var/lib/jenkins/war
find /var/lib/jenkins/plugins -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} +

journalctl --rotate || true
journalctl --vacuum-time=1s || true
find /var/log -type f -name "*.gz" -delete
find /var/log -type f -exec truncate -s 0 {} \;

# Identidade única por VM importada (machine-id é recriado no boot)
truncate -s 0 /etc/machine-id
rm -f /var/lib/dbus/machine-id
ln -s /etc/machine-id /var/lib/dbus/machine-id

rm -f /root/.bash_history "/home/${LAB_USER}/.bash_history"

# Devolve os blocos livres ao disco virtual (disco com discard habilitado)
sync
fstrim -av || true
