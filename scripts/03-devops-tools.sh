#!/usr/bin/env bash
# 03 - Ferramentas DevOps: Git, Python, VS Code, Docker + Compose, Terraform
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

$APT update
$APT install code \
             docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
             terraform


# ---------------------------------------------------------------- Ajustes Docker
# - logs dos containers com tamanho limitado (o disco não enche)
# - métricas do Docker em 127.0.0.1:9323 (o Prometheus do monitoramento lê)
# - imagens no overlay2: o "containerd image store" (padrão do Docker 29) guarda cada imagem
#   duas vezes (compactada + descompactada), o que deixava o .ova centenas de MB maior
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" },
  "metrics-addr": "127.0.0.1:9323",
  "features": { "containerd-snapshotter": false }
}
JSON
systemctl enable --now docker containerd
systemctl restart docker
usermod -aG docker "${LAB_USER}"

# Imagens mais usadas na aula e nos modelos do Painel já vêm baixadas:
# o primeiro "docker run" funciona na hora, mesmo com a internet da faculdade lenta
for img in nginx:alpine python:3.12-slim alpine:latest hello-world:latest; do
  for t in 1 2 3; do docker pull -q "$img" && break; echo "falhou baixar $img (tentativa $t)"; sleep 10; done
done
docker image ls
docker info --format 'Armazenamento das imagens: {{.Driver}}'

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
           ms-azuretools.vscode-docker hashicorp.terraform redhat.vscode-yaml; do
  timeout 300 sudo -u "${LAB_USER}" -H code --install-extension "$ext" --force || true
done
HOME_DIR="$(getent passwd "${LAB_USER}" | cut -d: -f6)"
install -d -o "${LAB_USER}" -g "${LAB_USER}" "${HOME_DIR}/.config" "${HOME_DIR}/.config/Code" "${HOME_DIR}/.config/Code/User" "${HOME_DIR}/.vscode"
install -m 0644 -o "${LAB_USER}" -g "${LAB_USER}" /tmp/files/gui/vscode-settings.json "${HOME_DIR}/.config/Code/User/settings.json"
install -m 0644 -o "${LAB_USER}" -g "${LAB_USER}" /tmp/files/gui/vscode-argv.json "${HOME_DIR}/.vscode/argv.json"
