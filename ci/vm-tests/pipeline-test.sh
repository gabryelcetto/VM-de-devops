#!/usr/bin/env bash
# Roda DENTRO da VM (como aluno): cria um pipeline no Jenkins que usa Docker e espera o resultado.
set -u
U=aluno:devops
B=http://localhost:8080
J="$(mktemp)"
crumb() {
  curl -s -c "$J" -b "$J" -u "$U" "$B/crumbIssuer/api/json" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["crumbRequestField"]+":"+d["crumb"])'
}
cat > /tmp/job.xml <<'XML'
<?xml version='1.1' encoding='UTF-8'?>
<flow-definition plugin="workflow-job">
  <description>Pipeline de teste do DevOps-Lab-UVV</description>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition" plugin="workflow-cps">
    <script>pipeline {
  agent any
  stages {
    stage('Docker') { steps { sh 'docker run --rm hello-world | grep "Hello from Docker"' } }
    stage('Ferramentas') { steps { sh 'git --version; python3 --version; terraform -version | head -n 1; ansible --version | head -n 1' } }
  }
}</script>
    <sandbox>true</sandbox>
  </definition>
</flow-definition>
XML
curl -s -c "$J" -b "$J" -u "$U" -H "$(crumb)" -H 'Content-Type: application/xml' \
  --data-binary @/tmp/job.xml "$B/createItem?name=teste-qa" -o /dev/null -w 'criar=%{http_code}\n'
curl -s -c "$J" -b "$J" -u "$U" -H "$(crumb)" -X POST "$B/job/teste-qa/build" -o /dev/null -w 'executar=%{http_code}\n'
r=""
for _ in $(seq 1 90); do
  r="$(curl -s -u "$U" "$B/job/teste-qa/1/api/json" 2>/dev/null \
      | python3 -c 'import json,sys; print(json.load(sys.stdin).get("result"))' 2>/dev/null)"
  if [ "$r" = SUCCESS ] || [ "$r" = FAILURE ] || [ "$r" = ABORTED ]; then break; fi
  sleep 5
done
echo "resultado=$r"
curl -s -u "$U" "$B/job/teste-qa/1/consoleText" | tail -n 25
