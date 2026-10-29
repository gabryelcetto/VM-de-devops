#!/usr/bin/env bash
# verificar-lab (versão Codespaces) - confere as ferramentas do DevOps-Lab-UVV
verde='\033[0;32m'; vermelho='\033[0;31m'; amarelo='\033[0;33m'; nc='\033[0m'
FALHAS=0
check() {
  local nome="$1"; shift; local saida
  if saida="$("$@" 2>&1)"; then
    printf "${verde}[OK]${nc}    %-16s %s\n" "$nome" "${saida%%$'\n'*}"
  else
    printf "${vermelho}[FALHA]${nc} %-16s %s\n" "$nome" "${saida%%$'\n'*}"; FALHAS=$((FALHAS+1))
  fi
}
echo "=== DevOps-Lab-UVV (Codespaces) - verificação do ambiente ==="
check "Ubuntu"          bash -c '. /etc/os-release; echo "$PRETTY_NAME"'
if v="$(code --version 2>/dev/null)" && [ -n "$v" ]; then
  printf "${verde}[OK]${nc}    %-16s %s\n" "VS Code" "${v%%$'\n'*}"
else
  printf "${amarelo}[INFO]${nc}  %-16s %s\n" "VS Code" "é o próprio editor do navegador"
fi
check "Docker"          docker --version
check "Docker Compose"  docker compose version
check "Git"             git --version
check "Ansible"         ansible --version
check "Terraform"       terraform -version
check "Python"          python3 --version
check "Docker roda"     bash -c "docker run --rm hello-world 2>/dev/null | grep 'Hello from Docker'"
code_http=""
for _ in $(seq 1 60); do
  code_http="$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/login)"
  [ "$code_http" = "200" ] && break; sleep 3
done
if [ "$code_http" = "200" ]; then printf "${verde}[OK]${nc}    %-16s %s\n" "Jenkins" "http://localhost:8080 (aba PORTAS)"
else printf "${vermelho}[FALHA]${nc} %-16s %s\n" "Jenkins" "não respondeu (HTTP $code_http)"; FALHAS=$((FALHAS+1)); fi
d="$(curl -s -o /dev/null -w '%{http_code}' http://localhost:6080/)"
if [ "$d" = "200" ]; then printf "${verde}[OK]${nc}    %-16s %s\n" "Área de trabalho" "porta 6080 (aba PORTAS), senha devops"
else printf "${vermelho}[FALHA]${nc} %-16s %s\n" "Área de trabalho" "porta 6080 não respondeu (HTTP $d)"; FALHAS=$((FALHAS+1)); fi
[ -s "$HOME/JENKINS-SENHA-INICIAL.txt" ] && echo "Senha inicial do Jenkins: $(cat "$HOME/JENKINS-SENHA-INICIAL.txt")"
exit "$FALHAS"
