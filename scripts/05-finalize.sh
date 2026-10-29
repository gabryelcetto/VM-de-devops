#!/usr/bin/env bash
# 05 - Ajustes finais: script de verificação, LEIA-ME na área de trabalho, rede via NetworkManager
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

# LEIA-ME na área de trabalho, com a senha inicial do Jenkins
JENKINS_PWD="$(cat /var/lib/jenkins/secrets/initialAdminPassword)"
sed "s/__JENKINS_PASSWORD__/${JENKINS_PWD}/" /tmp/files/LEIA-ME.txt > "${DESKTOP}/LEIA-ME.txt"
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

# Verificação final: o build falha se alguma ferramenta não estiver funcionando
sudo -u "${LAB_USER}" -H code --version
docker --version
docker compose version
git --version
ansible --version
terraform -version
python3 --version
java -version
systemctl is-active jenkins
