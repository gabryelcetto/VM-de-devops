#!/usr/bin/env bash
# 99 - Limpeza para deixar o .ova o menor possível
set -euxo pipefail

apt-get -y purge intel-microcode amd64-microcode || true
# ferramentas de perfil do kernel (não usadas no laboratório)
apt-get -y purge 'linux-tools-*' 'linux-cloud-tools-*' linux-tools-common 2>/dev/null || true
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
# documentação e traduções que vieram com o instalador do Ubuntu (antes da regra do 01-base)
find /usr/share/doc -type f ! -name copyright -delete 2>/dev/null || true
find /usr/share/doc -type d -empty -delete 2>/dev/null || true
find /usr/share/locale -mindepth 1 -maxdepth 1 -type d ! -name 'pt' ! -name 'pt_BR' ! -name 'en*' -exec rm -rf {} + 2>/dev/null || true
rm -rf /usr/share/info/* /usr/share/gtk-doc/* /usr/share/help/*
# VS Code: só as traduções da interface em português e inglês (as outras ~40 não são usadas)
find /usr/share/code/locales -name '*.pak' ! -name 'pt-BR.pak' ! -name 'en-US.pak' -delete 2>/dev/null || true
# VS Code: o Copilot embutido (173 MB) fica desligado ("chat.disableAIFeatures"); quem quiser instala
# "GitHub Copilot Chat" pela aba Extensões. Os .vsix baixados ao instalar as extensões são só cache.
rm -rf /usr/share/code/resources/app/extensions/copilot
rm -rf "/home/${LAB_USER}/.config/Code/CachedExtensionVSIXs" "/home/${LAB_USER}/.config/Code/logs"

# Jenkins: tira cache do instalador de plugins e as cópias "descompactadas" dos plugins
# e o jenkins.war aberto (o Jenkins recria tudo no primeiro boot; economiza ~150 MB no .ova)
systemctl stop jenkins || true
rm -rf /var/lib/jenkins/.cache /var/lib/jenkins/logs/* /var/lib/jenkins/war /var/cache/jenkins/war
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

# Swap: o que foi parar nela durante o build NÃO é espaço livre e iria para o .ova.
# Apaga, devolve os blocos ao disco (fstrim) e só então recria a swap vazia.
swapon --show || true
swapoff -a || true
rm -f /swap.img

# Devolve os blocos livres ao disco virtual (disco com discard habilitado)
sync
fstrim -av || true

fallocate -l 2G /swap.img && chmod 600 /swap.img && mkswap /swap.img
sync
echo "== espaço em disco no fim do build =="
df -h /
du -shx /usr/share/code /usr/lib/firefox /var/lib/jenkins /var/lib/docker /var/lib/containerd /opt /usr/lib/jvm /home 2>/dev/null || true
