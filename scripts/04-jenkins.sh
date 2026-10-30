#!/usr/bin/env bash
# 04 - Jenkins LTS pronto para uso:
#   - Java 21 (headless)
#   - plugins essenciais já instalados (sem o assistente que baixa tudo na aula)
#   - usuário aluno / senha devops
#   - memória limitada e prazo maior para iniciar em PCs lentos
set -euxo pipefail

APT="apt-get -y -o DPkg::Lock::Timeout=900 -o APT::Install-Recommends=false -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"
JHOME=/var/lib/jenkins

$APT install fontconfig openjdk-21-jre-headless

curl -fsSL https://pkg.jenkins.io/debian-stable/jenkins.io-2026.key \
  -o /etc/apt/keyrings/jenkins-keyring.asc
chmod a+r /etc/apt/keyrings/jenkins-keyring.asc
echo "deb [signed-by=/etc/apt/keyrings/jenkins-keyring.asc] https://pkg.jenkins.io/debian-stable binary/" \
  > /etc/apt/sources.list.d/jenkins.list

$APT update
$APT install jenkins
systemctl stop jenkins || true

# ---------------------------------------------------------------- serviço
mkdir -p /etc/systemd/system/jenkins.service.d
cat > /etc/systemd/system/jenkins.service.d/10-devops-lab.conf <<'UNIT'
[Service]
Environment="JAVA_OPTS=-Djava.awt.headless=true -Djenkins.install.runSetupWizard=false -Xms256m -Xmx768m -XX:+UseSerialGC -XX:TieredStopAtLevel=1 -XX:ReservedCodeCacheSize=64m"
# Em PCs lentos (VirtualBox com Hyper-V) o Jenkins pode levar vários minutos para subir
TimeoutStartSec=900
# Não disputa CPU com a área de trabalho
Nice=5
CPUWeight=50
IOWeight=50
UNIT
systemctl daemon-reload

# ---------------------------------------------------------------- usuário e configuração inicial
install -d -o jenkins -g jenkins "$JHOME/init.groovy.d"
cat > "$JHOME/init.groovy.d/01-devops-lab.groovy" <<'GROOVY'
import jenkins.model.*
import hudson.security.*
import jenkins.install.InstallState

def j = Jenkins.get()
def realm = j.getSecurityRealm()
if (!(realm instanceof HudsonPrivateSecurityRealm)) {
  realm = new HudsonPrivateSecurityRealm(false)
  j.setSecurityRealm(realm)
}
if (realm.getUser('aluno') == null) {
  realm.createAccount('aluno', 'devops')
}
def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
strategy.setAllowAnonymousRead(false)
j.setAuthorizationStrategy(strategy)
def loc = JenkinsLocationConfiguration.get()
loc.setUrl('http://localhost:8080/')
loc.save()
if (!j.getInstallState().isSetupComplete()) {
  InstallState.INITIAL_SETUP_COMPLETED.initializeState()
}
j.save()
// roda uma vez só
new File(j.getRootDir(), 'init.groovy.d/01-devops-lab.groovy').delete()
GROOVY
chown jenkins:jenkins "$JHOME/init.groovy.d/01-devops-lab.groovy"

# Evita a faixa "nova versão / assistente de atualização"
JV="$(dpkg-query -W -f='${Version}' jenkins)"
echo "$JV" > "$JHOME/jenkins.install.UpgradeWizard.state"
echo "$JV" > "$JHOME/jenkins.install.InstallUtil.lastExecVersion"
chown jenkins:jenkins "$JHOME"/jenkins.install.*

# ---------------------------------------------------------------- plugins
PM=/tmp/jenkins-plugin-manager.jar
PM_URL="$(curl -fsSL https://api.github.com/repos/jenkinsci/plugin-installation-manager-tool/releases/latest \
  | python3 -c 'import json,sys; print([a["browser_download_url"] for a in json.load(sys.stdin)["assets"] if a["name"].endswith(".jar")][0])' || true)"
[ -n "$PM_URL" ] || PM_URL="https://github.com/jenkinsci/plugin-installation-manager-tool/releases/download/2.13.2/jenkins-plugin-manager-2.13.2.jar"
curl -fsSL -o "$PM" "$PM_URL"
install -d -o jenkins -g jenkins "$JHOME/plugins"
PLUGINS="workflow-aggregator pipeline-stage-view git github docker-workflow credentials-binding timestamper ws-cleanup ansicolor ansible"
for try in 1 2 3; do
  # shellcheck disable=SC2086
  if sudo -u jenkins java -jar "$PM" --war /usr/share/java/jenkins.war \
       --plugin-download-directory "$JHOME/plugins" --plugins $PLUGINS; then break; fi
  echo "download de plugins falhou (tentativa $try)"; sleep 20
  [ "$try" = 3 ] && exit 1
done
rm -f "$PM"

# ---------------------------------------------------------------- liga e confere
systemctl enable jenkins
systemctl start jenkins
for _ in $(seq 1 150); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/login)" = "200" ] && break
  sleep 4
done
curl -fsS -o /dev/null http://localhost:8080/login
sleep 10
# login aluno/devops funciona e anônimo não entra
[ "$(curl -s -o /dev/null -w '%{http_code}' -u aluno:devops http://localhost:8080/api/json)" = "200" ]
[ "$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/api/json)" = "403" ]
# plugins essenciais carregados e ativos
curl -g -fsS -u aluno:devops 'http://localhost:8080/pluginManager/api/json?depth=1&tree=plugins[shortName,active]' > /tmp/plugins.json
python3 - <<'PY'
import json
d = json.load(open('/tmp/plugins.json'))
ativos = {p['shortName'] for p in d['plugins'] if p['active']}
precisa = {'workflow-aggregator', 'workflow-job', 'git', 'github', 'docker-workflow',
           'pipeline-stage-view', 'credentials-binding', 'timestamper', 'ws-cleanup', 'ansicolor', 'ansible'}
faltando = precisa - ativos
print(f"{len(ativos)} plugins ativos")
assert not faltando, f"plugins faltando/inativos: {faltando}"
PY
if journalctl -u jenkins --no-pager | grep -E "Failed Loading plugin|Failed to load"; then
  echo "ERRO: algum plugin do Jenkins falhou ao carregar"; exit 1
fi
test ! -e "$JHOME/init.groovy.d/01-devops-lab.groovy"

# Jenkins pode usar o Docker nos pipelines
usermod -aG docker jenkins
