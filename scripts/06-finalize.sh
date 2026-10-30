#!/usr/bin/env bash
# 06 - Ajustes finais: LEIA-ME e atalhos na Área de Trabalho, rede, boot rápido, serviços sob demanda
set -euxo pipefail

HOME_DIR="$(getent passwd "${LAB_USER}" | cut -d: -f6)"

# Comando "verificar-lab"
install -m 0755 /tmp/files/verificar-lab.sh /usr/local/bin/verificar-lab

# Pastas padrão em português (Área de Trabalho, Documentos...)
sudo -u "${LAB_USER}" -H env LANG=pt_BR.UTF-8 LC_ALL=pt_BR.UTF-8 xdg-user-dirs-update || true
DESKTOP="$(sudo -u "${LAB_USER}" -H xdg-user-dir DESKTOP 2>/dev/null || true)"
if [ -z "${DESKTOP}" ] || [ "${DESKTOP}" = "${HOME_DIR}" ]; then
  DESKTOP="${HOME_DIR}/Área de Trabalho"
fi
mkdir -p "${DESKTOP}" "${HOME_DIR}/projetos"

# LEIA-ME e atalhos na Área de Trabalho (marcados como confiáveis no login por devops-lab-login)
install -m 0644 /tmp/files/LEIA-ME.txt "${DESKTOP}/LEIA-ME.txt"
CODE_ID="$(cat /usr/share/devops-lab/code-desktop-id)"
for app in "$CODE_ID" firefox.desktop xfce4-terminal.desktop jenkins-devops-lab.desktop; do
  install -m 0755 "/usr/share/applications/$app" "${DESKTOP}/$app"
done
ln -sfn "${HOME_DIR}/projetos" "${DESKTOP}/projetos"
chown -R "${LAB_USER}:${LAB_USER}" "${HOME_DIR}"

# Rede gerenciada pelo NetworkManager (ícone de rede no painel).
# Só vale no próximo boot, então não derruba a conexão do Packer.
rm -f /etc/netplan/*.yaml
cat > /etc/netplan/01-network-manager-all.yaml <<'EOF'
network:
  version: 2
  renderer: NetworkManager
  ethernets:
    cabo-en:
      match:
        name: "en*"
      dhcp4: true
      optional: true
    cabo-eth:
      match:
        name: "eth*"
      dhcp4: true
      optional: true
EOF
chmod 600 /etc/netplan/01-network-manager-all.yaml
# No Ubuntu Server o NetworkManager ignora placas cabeadas; este arquivo vazio libera
mkdir -p /etc/NetworkManager/conf.d
: > /etc/NetworkManager/conf.d/10-globally-managed-devices.conf
systemctl disable systemd-networkd-wait-online.service || true

# Boot silencioso: no VirtualBox com Hyper-V ligado (ícone da tartaruga) cada linha
# de texto no console é muito lenta de desenhar e o boot parece travado.
sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT="quiet loglevel=3 systemd.show_status=auto rd.udev.log_level=3"/' /etc/default/grub
grep -q '^GRUB_CMDLINE_LINUX_DEFAULT=' /etc/default/grub \
  || echo 'GRUB_CMDLINE_LINUX_DEFAULT="quiet loglevel=3 systemd.show_status=auto rd.udev.log_level=3"' >> /etc/default/grub
sed -i '/^GRUB_RECORDFAIL_TIMEOUT=/d' /etc/default/grub
echo 'GRUB_RECORDFAIL_TIMEOUT=2' >> /etc/default/grub
echo 'kernel.printk = 3 3 1 3' > /etc/sysctl.d/10-console-silencioso.conf
update-grub
grep -q 'quiet loglevel=3' /boot/grub/grub.cfg

# Swap de 2 GB (fallocate não grava dados, então não aumenta o .ova)
if [ ! -f /swap.img ]; then
  fallocate -l 2G /swap.img && chmod 600 /swap.img && mkswap /swap.img
  grep -q '^/swap.img' /etc/fstab || echo '/swap.img none swap sw 0 0' >> /etc/fstab
fi

# zram: swap comprimida na RAM (bem mais rápida que o arquivo de swap no disco).
# Com VS Code + Docker + Jenkins + Firefox abertos em 4 GB, evita travadas por disco.
# O /swap.img continua como reserva (prioridade menor).
if modinfo zram >/dev/null 2>&1; then
  apt-get -y -o DPkg::Lock::Timeout=900 -o APT::Install-Recommends=false install systemd-zram-generator
  cat > /etc/systemd/zram-generator.conf <<'EOF'
[zram0]
zram-size = min(ram / 2, 2048)
compression-algorithm = zstd
swap-priority = 100
EOF
  # Com zram, trocar páginas pouco usadas para a RAM comprimida é barato
  printf 'vm.swappiness = 100\nvm.page-cluster = 0\n' > /etc/sysctl.d/60-devops-lab-zram.conf
else
  echo "AVISO: módulo zram não existe neste kernel; mantendo só o /swap.img"
fi

# cloud-init não é necessário depois da instalação (acelera o boot)
touch /etc/cloud/cloud-init.disabled

# Gera chaves SSH novas no primeiro boot de cada VM importada
# (não apagamos agora para não derrubar a conexão do Packer)
cat > /etc/systemd/system/regen-ssh-host-keys.service <<'EOF'
[Unit]
Description=Gera novas chaves de host SSH no primeiro boot
Before=ssh.service ssh.socket
ConditionPathExists=/etc/ssh/.regenerar-chaves

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'rm -f /etc/ssh/ssh_host_* && /usr/bin/ssh-keygen -A && rm -f /etc/ssh/.regenerar-chaves'

[Install]
WantedBy=multi-user.target
EOF
systemctl enable regen-ssh-host-keys.service
touch /etc/ssh/.regenerar-chaves

# ---------------------------------------------------------------- serviços sob demanda (boot rápido)
# Docker liga no primeiro uso (docker.socket), não no boot
systemctl disable docker.service containerd.service
systemctl enable docker.socket
# Jenkins liga 45 s depois do boot, para não disputar CPU com a área de trabalho
cat > /etc/systemd/system/jenkins-atrasado.timer <<'EOF'
[Unit]
Description=Liga o Jenkins logo depois que a área de trabalho abre

[Timer]
OnBootSec=45s
Unit=jenkins.service

[Install]
WantedBy=timers.target
EOF
systemctl disable jenkins.service
systemctl enable jenkins-atrasado.timer
# Lista de pacotes do apt atualizada em segundo plano (3 min após o boot e a cada 12 h),
# para "sudo apt install" funcionar sem erro mesmo sem "apt update"
cat > /etc/systemd/system/devops-lab-apt-update.service <<'EOF'
[Unit]
Description=Atualiza a lista de pacotes do apt em segundo plano
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
Nice=19
IOSchedulingClass=idle
ExecStart=/usr/bin/apt-get update -qq
EOF
cat > /etc/systemd/system/devops-lab-apt-update.timer <<'EOF'
[Unit]
Description=Atualiza a lista de pacotes do apt em segundo plano

[Timer]
OnBootSec=3min
OnUnitActiveSec=12h

[Install]
WantedBy=timers.target
EOF
systemctl enable devops-lab-apt-update.timer
# A rede passa a ser do NetworkManager; o systemd-networkd não é mais necessário
systemctl disable systemd-networkd.service systemd-networkd.socket systemd-networkd-wait-online.service 2>/dev/null || true
# Tarefas de manutenção que pesam no primeiro dia de uso
for t in man-db.timer motd-news.timer ua-timer.timer esm-cache.service apt-daily.timer apt-daily-upgrade.timer \
         rsyslog.service syslog.socket sysstat.service sysstat-collect.timer sysstat-summary.timer \
         e2scrub_all.timer e2scrub_reap.service dpkg-db-backup.timer; do
  systemctl disable "$t" 2>/dev/null || true
done
systemctl daemon-reload

# Verificação final: o build falha se alguma ferramenta não estiver funcionando
sudo -u "${LAB_USER}" -H code --version
docker --version
docker compose version
git --version
ansible --version
terraform -version
python3 --version
java -version
firefox --version
systemctl is-active jenkins
systemctl is-enabled jenkins-atrasado.timer docker.socket devops-lab-apt-update.timer
sudo -u "${LAB_USER}" -H code --list-extensions | tee /tmp/extensoes.txt
grep -qi ms-ceintl.vscode-language-pack-pt-br /tmp/extensoes.txt
grep -qi hashicorp.terraform /tmp/extensoes.txt
ansible-galaxy collection list 2>/dev/null | grep -E "community.general|community.docker|ansible.posix" || echo "AVISO: coleções do Ansible ausentes"
ls -l "${DESKTOP}"
