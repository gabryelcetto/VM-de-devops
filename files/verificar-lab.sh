#!/usr/bin/env bash
# verificar-lab - mostra as versões de todas as ferramentas do DevOps-Lab-UVV

verde='\033[0;32m'; vermelho='\033[0;31m'; nc='\033[0m'

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

if systemctl is-active --quiet jenkins; then
  printf "${verde}[OK]${nc}    %-16s %s\n" "Jenkins" "ativo em http://localhost:8080 (versão $(dpkg-query -W -f='${Version}' jenkins))"
else
  printf "${vermelho}[FALHA]${nc} %-16s %s\n" "Jenkins" "serviço parado (sudo systemctl start jenkins)"
fi

if docker info >/dev/null 2>&1; then
  printf "${verde}[OK]${nc}    %-16s %s\n" "Docker daemon" "rodando, usuário $(whoami) tem acesso"
else
  printf "${vermelho}[FALHA]${nc} %-16s %s\n" "Docker daemon" "sem acesso (faça logout/login ou: newgrp docker)"
fi
