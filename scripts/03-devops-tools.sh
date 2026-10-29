#!/usr/bin/env bash
# 03 - Ferramentas DevOps: Git, Python, VS Code, Docker + Compose, Terraform, Ansible
set -euxo pipefail

APT="apt-get -y -o DPkg::Lock::Timeout=900 -o APT::Install-Recommends=false -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"
CODENAME="$(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")"
ARCH="$(dpkg --print-architecture)"
install -m 0755 -d /etc/apt/keyrings

# ---------------------------------------------------------------- Git + Python
$APT install git python3 python3-pip python3-venv python-is-python3 pipx

# ---------------------------------------------------------------- VS Code
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
  | gpg --dearmor -o /etc/apt/keyrings/microsoft.gpg
chmod a+r /etc/apt/keyrings/microsoft.gpg
cat > /etc/apt/sources.list.d/vscode.sources <<EOF
Types: deb
URIs: https://packages.microsoft.com/repos/code
Suites: stable
Components: main
Architectures: amd64,arm64,armhf
Signed-By: /etc/apt/keyrings/microsoft.gpg
EOF
# evita que o pacote "code" crie um segundo arquivo de repositório
echo "code code/add-microsoft-repo boolean false" | debconf-set-selections

# ---------------------------------------------------------------- Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${CODENAME}
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
EOF

# ---------------------------------------------------------------- Terraform (HashiCorp)
curl -fsSL https://apt.releases.hashicorp.com/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/hashicorp-archive-keyring.gpg
chmod a+r /etc/apt/keyrings/hashicorp-archive-keyring.gpg
echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com ${CODENAME} main" \
  > /etc/apt/sources.list.d/hashicorp.list

# ---------------------------------------------------------------- Ansible (PPA oficial)
add-apt-repository -y ppa:ansible/ansible \
  || echo "AVISO: PPA do Ansible indisponível, usando a versão do Ubuntu"

$APT update
$APT install code \
             docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
             terraform \
             ansible-core

# ---------------------------------------------------------------- Coleções do Ansible
# ansible-core (~8 MB) + as coleções mais usadas em aula, no lugar do pacote
# "ansible" completo (~280 MB). Outras: ansible-galaxy collection install NOME
mkdir -p /usr/share/ansible/collections
for try in 1 2 3; do
  if ansible-galaxy collection install -p /usr/share/ansible/collections \
       community.general community.docker ansible.posix; then break; fi
  echo "ansible-galaxy falhou (tentativa $try)"; sleep 15
  [ "$try" = 3 ] && echo "AVISO: coleções do Ansible não instaladas"
done

# ---------------------------------------------------------------- Ajustes Docker
# Logs dos containers com tamanho limitado (o disco não enche)
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
JSON
systemctl enable --now docker containerd
systemctl restart docker
usermod -aG docker "${LAB_USER}"

# Atalho "docker-compose" (sintaxe antiga) -> "docker compose"
cat > /usr/local/bin/docker-compose <<'EOF'
#!/bin/sh
exec docker compose "$@"
EOF
chmod +x /usr/local/bin/docker-compose

# Autocompletar do Terraform para o usuário
sudo -u "${LAB_USER}" -H bash -c 'touch ~/.bashrc && terraform -install-autocomplete' || true

# ---------------------------------------------------------------- VS Code
# Extensões (falha de uma não interrompe o build; o teste confere depois)
for ext in ms-ceintl.vscode-language-pack-pt-br ms-python.python \
           ms-azuretools.vscode-docker hashicorp.terraform redhat.vscode-yaml redhat.ansible; do
  timeout 300 sudo -u "${LAB_USER}" -H code --install-extension "$ext" --force || true
done
HOME_DIR="$(getent passwd "${LAB_USER}" | cut -d: -f6)"
install -d -o "${LAB_USER}" -g "${LAB_USER}" "${HOME_DIR}/.config" "${HOME_DIR}/.config/Code" "${HOME_DIR}/.config/Code/User" "${HOME_DIR}/.vscode"
install -m 0644 -o "${LAB_USER}" -g "${LAB_USER}" /tmp/files/gui/vscode-settings.json "${HOME_DIR}/.config/Code/User/settings.json"
install -m 0644 -o "${LAB_USER}" -g "${LAB_USER}" /tmp/files/gui/vscode-argv.json "${HOME_DIR}/.vscode/argv.json"
