#!/usr/bin/env bash
# 07 - Painel DevOps (localhost:8090): um painel visual único para Docker, Jenkins, Git,
#      VS Code, Ansible, Terraform e Python, com modelos prontos, botões para criar/rodar/editar,
#      saída dos comandos ao vivo e gráficos. Só roda quando o aluno abre (não pesa no boot).
set -euxo pipefail

P=/tmp/files/painel
HOME_DIR="$(getent passwd "${LAB_USER}" | cut -d: -f6)"

# ---------------------------------------------------------------- Painel DevOps
install -d /usr/local/lib/devops-lab/painel
install -m 0644 "$P/painel.py" "$P/index.html" /usr/local/lib/devops-lab/painel/
install -m 0755 "$P/painel-devops.sh" /usr/local/bin/painel-devops
install -m 0644 "$P/painel-devops.desktop" /usr/share/applications/
install -D -m 0644 "$P/icone-painel.svg" /usr/share/icons/hicolor/scalable/apps/devops-lab-painel.svg
gtk-update-icon-cache -f -q /usr/share/icons/hicolor || true
python3 -m py_compile /usr/local/lib/devops-lab/painel/painel.py
rm -rf /usr/local/lib/devops-lab/painel/__pycache__

# Ligar/desligar Jenkins e Docker pelo painel sem pedir senha (só esses dois serviços)
install -D -m 0644 "$P/polkit-devops-lab.rules" /etc/polkit-1/rules.d/50-devops-lab.rules
sed -i "s/subject.user == \"aluno\"/subject.user == \"${LAB_USER}\"/" /etc/polkit-1/rules.d/50-devops-lab.rules

# Atalhos: área de trabalho e painel de baixo (lançador 15)
DESKTOP="$(sudo -u "${LAB_USER}" -H xdg-user-dir DESKTOP 2>/dev/null || true)"
if [ -z "${DESKTOP}" ] || [ "${DESKTOP}" = "${HOME_DIR}" ]; then DESKTOP="${HOME_DIR}/Área de Trabalho"; fi
install -m 0755 /usr/share/applications/painel-devops.desktop "${DESKTOP}/painel-devops.desktop"
for H in /etc/skel "$HOME_DIR"; do
  install -d "$H/.config/xfce4/panel/launcher-15"
  install -m 0644 /usr/share/applications/painel-devops.desktop "$H/.config/xfce4/panel/launcher-15/painel-devops.desktop"
  sed -i 's/^favorites=\(.*\)jenkins-devops-lab.desktop,/favorites=\1jenkins-devops-lab.desktop,painel-devops.desktop,/' \
    "$H/.config/xfce4/panel/whiskermenu-1.rc"
done
chown -R "${LAB_USER}:${LAB_USER}" "$HOME_DIR"

# Docker ligado durante o teste abaixo
systemctl start docker

# ---------------------------------------------------------------- teste do Painel DevOps (como o aluno)
PORTA=8099
sudo -u "${LAB_USER}" -H env PAINEL_PORTA=$PORTA python3 /usr/local/lib/devops-lab/painel/painel.py >/tmp/painel-teste.log 2>&1 &
PID=$!
for _ in $(seq 1 50); do curl -s -o /dev/null http://localhost:$PORTA/saude && break; sleep 0.2; done
api() { curl -sf "http://localhost:$PORTA$1"; }
api /api/docker | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["ligado"], d; print("painel docker OK:", len(d["containers"]), "containers")'
api /api/jenkins | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["respondendo"], d; print("painel jenkins OK:", len(d["jobs"]), "jobs")'
api /api/git >/dev/null && api /api/sistema >/dev/null && api /api/resumo >/dev/null
TOKEN="$(api / | sed -n 's/.*name="painel-token" content="\([^"]*\)".*/\1/p')"
test -n "$TOKEN"
acao() { curl -s -X POST "http://localhost:$PORTA$1" -H "X-Painel-Token: $TOKEN" -H 'Content-Type: application/json' -d "$2"; echo; }
acao /api/jenkins '{"acao":"criar","job":"teste-painel"}' | grep -q '"ok": true'
acao /api/jenkins '{"acao":"construir","job":"teste-painel"}' | grep -q '"ok": true'
OK=0
for _ in $(seq 1 60); do
  if acao /api/jenkins '{"acao":"console","job":"teste-painel"}' | grep -q 'Finished: SUCCESS'; then OK=1; break; fi
  sleep 3
done
acao /api/jenkins '{"acao":"console","job":"teste-painel"}' | tail -c 600
acao /api/jenkins '{"acao":"apagar","job":"teste-painel"}'
test "$OK" = 1
# Ansible, Terraform e Python pelo painel (tarefas com saída ao vivo)
espera() {  # $1 = resposta do /api/executar ; imprime a saída e falha se o comando falhou
  local id; id="$(echo "$1" | python3 -c 'import json,sys; print(json.load(sys.stdin)["resultado"]["tarefa"])')"
  for _ in $(seq 1 120); do
    api "/api/tarefa?id=$id" | python3 -c 'import json,sys; t=json.load(sys.stdin); sys.exit(0 if t["fim"] else 1)' && break; sleep 1
  done
  api "/api/tarefa?id=$id" | python3 -c 'import json,sys; t=json.load(sys.stdin); print("\n".join(t["linhas"][-15:])); print("codigo", t["codigo"]); sys.exit(t["codigo"])'
}
acao /api/arquivo '{"acao":"projeto","nome":"teste-painel-ansible","arquivos":{"playbook.yml":"- name: Teste\n  hosts: localhost\n  gather_facts: false\n  tasks:\n    - name: ping\n      ansible.builtin.ping:\n"}}'
espera "$(acao /api/executar "{\"ferramenta\":\"ansible\",\"acao\":\"rodar\",\"playbook\":\"$HOME_DIR/projetos/teste-painel-ansible/playbook.yml\"}")"
acao /api/arquivo '{"acao":"projeto","nome":"teste-painel-tf","arquivos":{"main.tf":"resource \"terraform_data\" \"x\" {\n  input = \"ok\"\n}\noutput \"x\" {\n  value = terraform_data.x.output\n}\n"}}'
espera "$(acao /api/executar "{\"ferramenta\":\"terraform\",\"acao\":\"init\",\"pasta\":\"$HOME_DIR/projetos/teste-painel-tf\"}")"
espera "$(acao /api/executar "{\"ferramenta\":\"terraform\",\"acao\":\"apply\",\"pasta\":\"$HOME_DIR/projetos/teste-painel-tf\"}")"
api /api/terraform | grep -q 'terraform_data.x'
acao /api/arquivo '{"acao":"projeto","nome":"teste-painel-py","arquivos":{"main.py":"print(\"python ok\")\n"}}'
espera "$(acao /api/executar "{\"ferramenta\":\"python\",\"acao\":\"rodar\",\"pasta\":\"$HOME_DIR/projetos/teste-painel-py\",\"script\":\"$HOME_DIR/projetos/teste-painel-py/main.py\"}")" | grep -q "python ok"
rm -rf "$HOME_DIR"/projetos/teste-painel-*
# sem token, nada é alterado
curl -s -X POST "http://localhost:$PORTA/api/git" -d '{}' | grep -q 'Token inválido'
kill "$PID" || true
cat /tmp/painel-teste.log | tail -n 20
echo "Painéis instalados."
