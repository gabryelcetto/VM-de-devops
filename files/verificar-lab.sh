#!/usr/bin/env bash
# verificar-lab - mostra as versões de todas as ferramentas do DevOps-Lab-UVV (inclui Firefox)

verde='\033[0;32m'; vermelho='\033[0;31m'; amarelo='\033[0;33m'; nc='\033[0m'

check() {
  local nome="$1"; shift
  local saida
  if saida="$("$@" 2>&1)"; then
    saida="${saida%%$'\n'*}"
    printf "${verde}[OK]${nc}    %-16s %s\n" "$nome" "$saida"
  else
    printf "${vermelho}[FALHA]${nc} %-16s %s\n" "$nome" "$saida"
  fi
}

echo "=== DevOps-Lab-UVV - verificação do ambiente ==="
check "Ubuntu"          lsb_release -ds
check "VS Code"         code --version
check "Docker"          docker --version
check "Docker Compose"  docker compose version
check "Git"             git --version
check "Ansible"         ansible --version
check "Terraform"       terraform -version
check "Python"          python3 --version
check "pip"             pip3 --version
check "Java"            java -version
check "Firefox"         firefox --version

codigo="$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/login 2>/dev/null)"
if [ "$codigo" = "200" ]; then
  printf "${verde}[OK]${nc}    %-16s %s\n" "Jenkins" "http://localhost:8080 (aluno / devops) - versão $(dpkg-query -W -f='${Version}' jenkins)"
elif systemctl is-active --quiet jenkins || systemctl is-active --quiet jenkins-atrasado.timer; then
  printf "${amarelo}[AGUARDE]${nc} %-14s %s\n" "Jenkins" "ligando (sobe ~1 min depois do boot); rode verificar-lab de novo daqui a pouco"
else
  printf "${vermelho}[FALHA]${nc} %-16s %s\n" "Jenkins" "parado (sudo systemctl start jenkins)"
fi

if docker info >/dev/null 2>&1; then
  printf "${verde}[OK]${nc}    %-16s %s\n" "Docker daemon" "rodando, usuário $(whoami) tem acesso"
else
  printf "${vermelho}[FALHA]${nc} %-16s %s\n" "Docker daemon" "sem acesso (faça logout/login ou: newgrp docker)"
fi
