#!/usr/bin/env bash
# Laboratório do Painel: monta no runner do GitHub uma cópia "sem tela" da VM
# (usuário aluno, Docker, Jenkins pelo MESMO script da VM, Terraform, Python, monitoramento)
# e liga o Painel DevOps como o aluno, para os testes de ponta a ponta (e2e.js).
# Uso (no runner): sudo bash ci/lab/preparar.sh
set -euxo pipefail
export LAB_USER=aluno DEBIAN_FRONTEND=noninteractive
APT="apt-get -y -qq -o DPkg::Lock::Timeout=600 -o APT::Install-Recommends=false"

id aluno >/dev/null 2>&1 || useradd -m -s /bin/bash aluno
echo aluno:devops | chpasswd
usermod -aG docker,systemd-journal aluno
mkdir -p /etc/apt/keyrings

# Java 21 como padrão (o runner vem com outros JDKs)
apt-get update -qq
$APT install openjdk-21-jre-headless fontconfig python3-venv python3-pip git curl jq
update-alternatives --set java /usr/lib/jvm/java-21-openjdk-amd64/bin/java

# Terraform como na VM (scripts/03-devops-tools.sh)
curl -fsSL https://apt.releases.hashicorp.com/gpg | gpg --dearmor --yes -o /etc/apt/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/etc/apt/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(. /etc/os-release; echo "$VERSION_CODENAME") main" \
  > /etc/apt/sources.list.d/hashicorp.list
apt-get update -qq
$APT install terraform

# Docker: métricas em 127.0.0.1:9323 como na VM (o Prometheus lê). Junta com o daemon.json do runner.
mkdir -p /etc/docker
[ -s /etc/docker/daemon.json ] || echo '{}' > /etc/docker/daemon.json
jq '. + {"metrics-addr": "127.0.0.1:9323"}' /etc/docker/daemon.json > /tmp/daemon.json
mv /tmp/daemon.json /etc/docker/daemon.json
cat /etc/docker/daemon.json
systemctl restart docker
for _ in $(seq 1 30); do curl -fsS -o /dev/null http://127.0.0.1:9323/metrics && break; sleep 1; done

# Monitoramento: exatamente o script da VM (baixa as imagens, testa e deixa desligado)
rm -rf /tmp/files && mkdir -p /tmp/files && cp -r files/monitoramento /tmp/files/
LAB_USER=aluno bash scripts/08-monitoramento.sh

# Jenkins: exatamente o script da VM. Na VM o grupo docker do Jenkins vale depois do
# reboot; aqui reiniciamos o serviço para valer na hora.
LAB_USER=aluno bash scripts/04-jenkins.sh
systemctl restart jenkins
for _ in $(seq 1 120); do [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/login)" = 200 ] && break; sleep 3; done

# Painel DevOps (como em scripts/07-paineis.sh)
install -d /usr/local/lib/devops-lab/painel
install -m 0644 files/painel/painel.py files/painel/index.html /usr/local/lib/devops-lab/painel/
install -m 0755 files/painel/painel-devops.sh /usr/local/bin/painel-devops
install -D -m 0644 files/painel/polkit-devops-lab.rules /etc/polkit-1/rules.d/50-devops-lab.rules
python3 -m py_compile /usr/local/lib/devops-lab/painel/painel.py
rm -rf /usr/local/lib/devops-lab/painel/__pycache__

# Liga o Painel como o aluno (porta 8090, a mesma da VM), medindo a cobertura de código:
# ao final do laboratório dá para ver quais linhas e ramos do painel.py os testes usaram.
pip install -q --break-system-packages coverage
install -d -m 0777 /tmp/cobertura
cp pyproject.toml /tmp/cobertura/pyproject.toml
sudo -u aluno -H env XDG_CONFIG_HOME=/home/aluno/.config COVERAGE_FILE=/tmp/cobertura/.coverage.e2e bash -c \
  'cd ~ && setsid -f python3 -m coverage run --rcfile=/tmp/cobertura/pyproject.toml /usr/local/lib/devops-lab/painel/painel.py > /tmp/painel.log 2>&1 < /dev/null'
for _ in $(seq 1 100); do curl -s -o /dev/null http://localhost:8090/saude && break; sleep 0.3; done
curl -fsS http://localhost:8090/saude
echo "Laboratório pronto."
