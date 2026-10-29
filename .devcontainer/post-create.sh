#!/usr/bin/env bash
# Instala o que não vem pronto nas "features": Ansible e o comando verificar-lab
set -euxo pipefail
pipx install --include-deps ansible || pip install --user ansible
sudo install -m 0755 .devcontainer/verificar-lab.sh /usr/local/bin/verificar-lab
sudo install -m 0755 .devcontainer/senha-jenkins.sh /usr/local/bin/senha-jenkins
mkdir -p "$HOME/projetos"
