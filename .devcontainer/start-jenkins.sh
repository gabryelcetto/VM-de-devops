#!/usr/bin/env bash
# Sobe o Jenkins LTS como container (porta 8080) sempre que o Codespace liga
set -uo pipefail
for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 2; done
if docker ps -a --format '{{.Names}}' | grep -qx jenkins; then
  docker start jenkins >/dev/null
else
  docker run -d --name jenkins --restart unless-stopped \
    -p 8080:8080 -v jenkins_home:/var/jenkins_home \
    jenkins/jenkins:lts-jdk21 >/dev/null
fi
echo "Jenkins iniciando em http://localhost:8080 (aba PORTAS). Senha inicial: rode  senha-jenkins"
