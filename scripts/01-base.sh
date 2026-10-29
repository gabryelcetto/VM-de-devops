#!/usr/bin/env bash
# 01 - Sistema base enxuto (alvo: .ova final <= 3,8 GB)
set -euxo pipefail

APT="apt-get -y -o DPkg::Lock::Timeout=900 -o APT::Install-Recommends=false -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"

# Espera o cloud-init do primeiro boot e libera o apt
cloud-init status --wait || true
systemctl stop unattended-upgrades.service apt-daily.timer apt-daily-upgrade.timer || true
systemctl disable unattended-upgrades.service apt-daily.timer apt-daily-upgrade.timer || true

# Não instalar recomendados nem documentação (economiza centenas de MB)
cat > /etc/apt/apt.conf.d/99-devops-lab-enxuto <<'EOF'
APT::Install-Recommends "false";
APT::Install-Suggests "false";
EOF
cat > /etc/dpkg/dpkg.cfg.d/99-devops-lab-sem-docs <<'EOF'
path-exclude=/usr/share/doc/*
path-include=/usr/share/doc/*/copyright
path-exclude=/usr/share/info/*
path-exclude=/usr/share/help/*
path-exclude=/usr/share/gtk-doc/*
path-exclude=/usr/share/locale/*
path-include=/usr/share/locale/pt_BR/*
path-include=/usr/share/locale/pt/*
path-include=/usr/share/locale/en*/*
path-include=/usr/share/locale/locale.alias
EOF

$APT update
$APT full-upgrade

$APT install \
  ca-certificates curl wget gnupg lsb-release software-properties-common \
  unzip zip jq tree htop vim-tiny nano make \
  net-tools dnsutils iputils-ping bash-completion \
  virtualbox-guest-utils virtualbox-guest-x11

# Kernel "virtual": numa VM não precisa do linux-firmware (~1 GB) nem do
# linux-modules-extra (~107 MB). Todos os drivers usados (vmwgfx, vboxvideo, vboxguest,
# vboxsf, e1000, ahci, overlay/bridge/netfilter do Docker) estão no linux-modules.
$APT install linux-virtual
apt-get -y purge linux-generic linux-image-generic linux-headers-generic linux-firmware || true
apt-get -y purge 'linux-headers-*' || true
apt-get -y purge 'linux-modules-extra-*' || true
for m in vmwgfx vboxvideo vboxguest vboxsf e1000 ahci overlay br_netfilter veth; do
  modinfo -k "$(ls /lib/modules | sort -V | tail -n 1)" "$m" >/dev/null   # falha o build se faltar algum
done

# Remover o snapd também remove o metapacote ubuntu-server-minimal; marcamos
# como "manual" os pacotes essenciais que ele puxava para o autoremove não apagá-los
for pkg in sudo systemd-resolved dbus apparmor netbase systemd systemd-sysv udev \
           e2fsprogs apt openssh-server ubuntu-minimal locales language-pack-pt; do
  if dpkg -s "$pkg" >/dev/null 2>&1; then apt-mark manual "$pkg"; fi
done

# snapd não é usado (economiza espaço e acelera o boot)
apt-get -y purge snapd || true
rm -rf /snap /var/snap /var/lib/snapd /var/cache/snapd
cat > /etc/apt/preferences.d/no-snapd <<'EOF'
Package: snapd
Pin: release a=*
Pin-Priority: -10
EOF

usermod -aG vboxsf "${LAB_USER}" || true

# Sem perguntas interativas do needrestart quando o aluno usar o apt
if [ -d /etc/needrestart ]; then
  mkdir -p /etc/needrestart/conf.d
  printf "\$nrconf{restart} = 'a';\n\$nrconf{kernelhints} = 0;\n" > /etc/needrestart/conf.d/90-devops-lab.conf
fi
# Desliga e para mais rápido; logs com tamanho limitado
mkdir -p /etc/systemd/system.conf.d /etc/systemd/journald.conf.d
printf '[Manager]\nDefaultTimeoutStopSec=15s\n' > /etc/systemd/system.conf.d/10-devops-lab.conf
printf '[Journal]\nSystemMaxUse=100M\n' > /etc/systemd/journald.conf.d/10-devops-lab.conf
# Sem propaganda do Ubuntu Pro na saída do apt
pro config set apt_news=false 2>/dev/null || true
