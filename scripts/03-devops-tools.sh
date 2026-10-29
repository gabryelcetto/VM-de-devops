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
             ansible

# ---------------------------------------------------------------- Ajustes Docker
systemctl enable --now docker containerd
usermod -aG docker "${LAB_USER}"

# Atalho "docker-compose" (sintaxe antiga) -> "docker compose"
cat > /usr/local/bin/docker-compose <<'EOF'
#!/bin/sh
exec docker compose "$@"
EOF
chmod +x /usr/local/bin/docker-compose

# Autocompletar do Terraform para o usuário
sudo -u "${LAB_USER}" -H bash -c 'touch ~/.bashrc && terraform -install-autocomplete' || true

# Extensões úteis no VS Code (falha não interrompe o build)
# (só extensões leves, para manter o .ova <= 3,8 GB)
for ext in ms-azuretools.vscode-docker hashicorp.terraform redhat.vscode-yaml; do
  timeout 300 sudo -u "${LAB_USER}" -H code --install-extension "$ext" --force || true
done
