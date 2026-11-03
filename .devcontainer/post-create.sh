#!/usr/bin/env bash
# Instala o que não vem pronto nas "features": o comando verificar-lab
set -euxo pipefail
sudo install -m 0755 .devcontainer/verificar-lab.sh /usr/local/bin/verificar-lab
sudo install -m 0755 .devcontainer/senha-jenkins.sh /usr/local/bin/senha-jenkins
mkdir -p "$HOME/projetos"
