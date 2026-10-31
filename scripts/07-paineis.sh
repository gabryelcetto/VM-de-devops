#!/usr/bin/env bash
# 07 - Painéis visuais:
#   - Painel DevOps (localhost:8090): Docker, Jenkins, Git, VS Code e Sistema em um só lugar,
#     com ações (criar/parar containers, editar compose, criar/editar/rodar pipelines, commit...)
#   - Portainer CE (localhost:9000): painel completo do Docker. Usuário admin / senha devops.
# Os dois só rodam quando o aluno abre (nada fica pesando no boot).
set -euxo pipefail

P=/tmp/files/painel
HOME_DIR="$(getent passwd "${LAB_USER}" | cut -d: -f6)"

# ---------------------------------------------------------------- Painel DevOps
install -d /usr/local/lib/devops-lab/painel
install -m 0644 "$P/painel.py" "$P/index.html" /usr/local/lib/devops-lab/painel/
install -m 0755 "$P/painel-devops.sh" /usr/local/bin/painel-devops
install -m 0755 "$P/abrir-portainer.sh" /usr/local/bin/abrir-portainer
install -m 0644 "$P/painel-devops.desktop" "$P/portainer-devops-lab.desktop" /usr/share/applications/
install -D -m 0644 "$P/icone-painel.svg" /usr/share/icons/hicolor/scalable/apps/devops-lab-painel.svg
install -D -m 0644 "$P/icone-docker.svg" /usr/share/icons/hicolor/scalable/apps/devops-lab-docker.svg
gtk-update-icon-cache -f -q /usr/share/icons/hicolor || true
python3 -m py_compile /usr/local/lib/devops-lab/painel/painel.py
rm -rf /usr/local/lib/devops-lab/painel/__pycache__

# Ligar/desligar Jenkins e Docker pelo painel sem pedir senha (só esses dois serviços)
install -D -m 0644 "$P/polkit-devops-lab.rules" /etc/polkit-1/rules.d/50-devops-lab.rules
sed -i "s/subject.user == \"aluno\"/subject.user == \"${LAB_USER}\"/" /etc/polkit-1/rules.d/50-devops-lab.rules

# Atalhos: área de trabalho e painel de baixo (lançadores 15 e 16)
DESKTOP="$(sudo -u "${LAB_USER}" -H xdg-user-dir DESKTOP 2>/dev/null || true)"
if [ -z "${DESKTOP}" ] || [ "${DESKTOP}" = "${HOME_DIR}" ]; then DESKTOP="${HOME_DIR}/Área de Trabalho"; fi
for app in painel-devops.desktop portainer-devops-lab.desktop; do
  install -m 0755 "/usr/share/applications/$app" "${DESKTOP}/$app"
done
for H in /etc/skel "$HOME_DIR"; do
  for pair in 15:painel-devops.desktop 16:portainer-devops-lab.desktop; do
    id="${pair%%:*}"; app="${pair#*:}"
    install -d "$H/.config/xfce4/panel/launcher-$id"
    install -m 0644 "/usr/share/applications/$app" "$H/.config/xfce4/panel/launcher-$id/$app"
  done
  sed -i 's/^favorites=\(.*\)jenkins-devops-lab.desktop,/favorites=\1jenkins-devops-lab.desktop,painel-devops.desktop,portainer-devops-lab.desktop,/' \
    "$H/.config/xfce4/panel/whiskermenu-1.rc"
done
chown -R "${LAB_USER}:${LAB_USER}" "$HOME_DIR"

# ---------------------------------------------------------------- Portainer
systemctl start docker
docker pull -q portainer/portainer-ce:lts
docker rm -f portainer 2>/dev/null || true
docker volume rm portainer_data 2>/dev/null || true
docker volume create portainer_data
# senha "devops" (bcrypt); o Portainer só usa isto na primeira vez
SENHA_HASH='$2a$10$IB8u9sOk.lEYCIMGvtTchuoyssiejjqCG8DdBVTDHUhImgIueQiwS'
docker run -d --name portainer --restart=no -p 127.0.0.1:9000:9000 \
  -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data \
  portainer/portainer-ce:lts --http-enabled --admin-password "$SENHA_HASH"
for _ in $(seq 1 90); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:9000/api/system/status)" = "200" ] && break
  sleep 2
done
docker logs portainer 2>&1 | tail -n 20
JWT="$(curl -sf -X POST http://127.0.0.1:9000/api/auth -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"devops"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["jwt"])')"
test -n "$JWT"
AUTH="Authorization: Bearer $JWT"
# Ambiente "local" (o Docker desta VM) já cadastrado: o aluno não passa pelo assistente inicial
curl -sf -X POST http://127.0.0.1:9000/api/endpoints -H "$AUTH" \
  -F Name=local -F EndpointCreationType=1 | python3 -c 'import json,sys; print("ambiente:", json.load(sys.stdin)["Name"])'
# Sem telemetria e aceitando a senha curta padrão do Lab (não pede para trocar no login)
curl -s -X PUT http://127.0.0.1:9000/api/settings -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"EnableTelemetry": false, "InternalAuthSettings": {"RequiredPasswordLength": 6}}' | head -c 300 || true
echo
curl -sf http://127.0.0.1:9000/api/endpoints -H "$AUTH" | python3 -c 'import json,sys; e=json.load(sys.stdin); print(len(e), "ambiente(s)"); assert e'
docker stop portainer
# O arquivo do container: o Portainer não liga sozinho no boot
test "$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' portainer)" = "no"

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
# sem token, nada é alterado
curl -s -X POST "http://localhost:$PORTA/api/git" -d '{}' | grep -q 'Token inválido'
kill "$PID" || true
cat /tmp/painel-teste.log | tail -n 20
echo "Painéis instalados."
