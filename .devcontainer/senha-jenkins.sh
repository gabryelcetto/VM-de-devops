#!/usr/bin/env bash
# Mostra a senha inicial do Jenkins (Codespaces). Espera o Jenkins ligar, se preciso.
for i in $(seq 1 60); do
  if s="$(docker exec jenkins cat /var/jenkins_home/secrets/initialAdminPassword 2>/dev/null)" && [ -n "$s" ]; then
    echo "Senha inicial do Jenkins: $s"; exit 0
  fi
  if [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/login)" = "200" ] \
     && ! docker exec jenkins test -f /var/jenkins_home/secrets/initialAdminPassword 2>/dev/null; then
    echo "O Jenkins já foi configurado (a senha inicial não existe mais). Use o usuário que você criou."; exit 0
  fi
  [ "$i" = 1 ] && echo "Aguardando o Jenkins ligar..."
  sleep 3
done
echo "O Jenkins ainda não ligou. Rode: bash .devcontainer/start-jenkins.sh  e tente de novo."; exit 1
