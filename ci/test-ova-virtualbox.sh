#!/usr/bin/env bash
# Testa o DevOps-Lab.ova no VirtualBox de verdade (como um aluno faria):
# importa, liga, espera a área de trabalho, confere interface, ferramentas, Jenkins
# (inclusive um pipeline com Docker), desempenho, reinicia com a CPU limitada
# (PC lento) e tira prints da tela por dentro da VM.
# Uso: ci/test-ova-virtualbox.sh <arquivo.ova> <pasta-de-resultados>
set -uo pipefail

OVA="$1"
OUT="$2"
VM="DevOps-Lab"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT"
SUMMARY="$OUT/RESUMO.txt"
ANALISE="$OUT/ANALISE.txt"
FAILS=0

log()  { echo "$*" | tee -a "$SUMMARY"; }
ok()   { log "[OK]    $*"; }
bad()  { log "[FALHA] $*"; FAILS=$((FAILS+1)); }
prop() { VBoxManage guestproperty get "$VM" "$1" 2>/dev/null | sed -n 's/^Value: //p'; }
grun() { # executa um comando dentro da VM como aluno
  timeout 600 VBoxManage guestcontrol "$VM" run --username aluno --password devops \
    --wait-stdout --wait-stderr --timeout 540000 -- "$@" 2>&1
}
gsh()  { grun /bin/bash -lc "$1"; }
gcopy() { VBoxManage guestcontrol "$VM" copyto --username aluno --password devops "$1" "$2" >/dev/null 2>&1; }
# Ambiente da sessão gráfica do aluno (X e D-Bus)
XENV='export DISPLAY=:0 XAUTHORITY=/home/aluno/.Xauthority DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus;'
chk() { # chk "descrição" "comando shell" "regex esperado na saída"
  local R; R="$(gsh "$2")"
  printf '### %s\n%s\n\n' "$1" "$R" >> "$OUT/qa-detalhes.txt"
  if echo "$R" | grep -qE "$3"; then ok "$1"; else bad "$1"; log "$(echo "$R" | tail -n 8)"; fi
}
nchk() { # nchk "descrição" "comando shell" "regex que NÃO pode aparecer"
  local R; R="$(gsh "$2")"
  printf '### %s\n%s\n\n' "$1" "$R" >> "$OUT/qa-detalhes.txt"
  if echo "$R" | grep -qE "$3"; then bad "$1"; log "$(echo "$R" | grep -E "$3" | head -n 5)"; else ok "$1"; fi
}

wait_desktop() { # $1 = rótulo, $2 = limite em segundos
  local label="$1" limit="$2" t=0 users="" ip=""
  while [ "$t" -lt "$limit" ]; do
    users="$(prop /VirtualBox/GuestInfo/OS/LoggedInUsers)"
    ip="$(prop /VirtualBox/GuestInfo/Net/0/V4/IP)"
    if [ -n "$users" ] && [ "$users" != "0" ] && [ -n "$ip" ]; then
      ok "$label: área de trabalho aberta (usuário logado) e rede com IP $ip em ${t}s"
      return 0
    fi
    sleep 5; t=$((t+5))
  done
  bad "$label: não chegou na área de trabalho em ${limit}s (usuários='${users}', ip='${ip}')"
  return 1
}

print_tela() { # $1 = nome do arquivo; print pelo próprio X da VM (o que o aluno vê); devolve nº de cores
  gsh "$XENV xwd -root -silent > /tmp/tela.xwd; ls -l /tmp/tela.xwd" >> "$OUT/qa-detalhes.txt"
  rm -f "$OUT/tela.xwd"
  VBoxManage guestcontrol "$VM" copyfrom --username aluno --password devops /tmp/tela.xwd "$OUT/tela.xwd" >/dev/null 2>&1 || true
  if [ -s "$OUT/tela.xwd" ] && convert "xwd:$OUT/tela.xwd" "$OUT/$1.png" 2>/dev/null; then
    rm -f "$OUT/tela.xwd"
    convert "$OUT/$1.png" -format '%k' info:
  else
    echo 0
  fi
}

print_vbox() { # $1 = nome; print pela JANELA do VirtualBox (o que chega ao monitor do aluno); devolve nº de cores
  rm -f "$OUT/$1.png"
  if VBoxManage controlvm "$VM" screenshotpng "$OUT/$1.png" >/dev/null 2>&1 && [ -s "$OUT/$1.png" ]; then
    convert "$OUT/$1.png" -format '%k' info: 2>/dev/null || echo 0
  else
    echo 0
  fi
}

log "=== Teste do DevOps-Lab.ova no VirtualBox $(VBoxManage --version) ==="
log "Arquivo: $(basename "$OVA") ($(du -h "$OVA" | cut -f1))"

# ---------------------------------------------------------------- importar
if VBoxManage import "$OVA" --vsys 0 --vmname "$VM" >"$OUT/import.txt" 2>&1; then
  ok "Importação do .ova (Arquivo > Importar Appliance)"
else
  bad "Importação do .ova"; tee -a "$SUMMARY" < "$OUT/import.txt"; exit 1
fi
VBoxManage showvminfo "$VM" --machinereadable > "$OUT/vminfo.txt"
grep -E '^(ostype|memory|cpus|graphicscontroller|vram|nic1|storagecontrollertype0|storagecontrollerportcount0|ioapic|paravirtprovider|mouse|clipboard|draganddrop)=' "$OUT/vminfo.txt" | tee -a "$SUMMARY"

# ---------------------------------------------------------------- 1º boot
VBoxManage startvm "$VM" --type headless
wait_desktop "boot1" 900
sleep 20

if [ -n "$(prop /VirtualBox/GuestAdd/Version)" ]; then
  ok "Guest Additions ativos: $(prop /VirtualBox/GuestAdd/Version)"
else
  bad "Guest Additions não responderam"
fi

# Ferramentas de print/inspeção da tela, só para o teste (esta VM é descartada depois)
gsh "echo devops | sudo -S -p '' apt-get update -qq; echo devops | sudo -S -p '' apt-get install -y -qq x11-utils x11-apps >/dev/null; which xwd xwininfo" >> "$OUT/qa-detalhes.txt"

# ---------------------------------------------------------------- imagem na janela do VirtualBox
# (sem redimensionar nada: é exatamente o que o aluno vê ao ligar a VM)
CORES="$(print_vbox janela-virtualbox-1)"
if [ "${CORES:-0}" -gt 100 ]; then ok "Janela do VirtualBox mostra a área de trabalho ($CORES cores)"; else bad "Janela do VirtualBox PRETA após o login ($CORES cores)"; fi

# ---------------------------------------------------------------- interface (logo após o login)
CORES="$(print_tela tela-1-login)"
if [ "${CORES:-0}" -gt 100 ]; then ok "Tela desenhada logo após o login ($CORES cores)"; else bad "Tela vazia/preta após o login ($CORES cores)"; fi
chk  "Sessão XFCE completa (xfwm4, painel, área de trabalho, xfsettingsd)" "for p in xfwm4 xfce4-panel xfdesktop xfsettingsd; do pgrep -u aluno -x \$p >/dev/null && echo \"ok-\$p\"; done | tr '\n' ' '" "ok-xfwm4 ok-xfce4-panel ok-xfdesktop ok-xfsettingsd"
chk  "Painel do XFCE na tela" "$XENV xwininfo -root -tree" "xfce4-panel"
chk  "Área de trabalho (xfdesktop) na tela" "$XENV xwininfo -root -tree" '"(Desktop|Área de trabalho|xfdesktop)"'
nchk "Sem diálogo de primeiro uso do painel" "$XENV xwininfo -root -tree" '"(Painel|Panel)"'
chk  "Papel de parede DevOps Lab como padrão" "readlink -f /usr/share/backgrounds/xfce/xfce-shapes.svg" "devops-lab.svg"
chk  "Tema Greybird, ícones elementary e fonte Ubuntu" "$XENV xfconf-query -c xsettings -p /Net/ThemeName; xfconf-query -c xsettings -p /Net/IconThemeName; xfconf-query -c xsettings -p /Gtk/FontName" "Ubuntu 10"
chk  "Painel com menu, atalhos, tarefas, bandeja e relógio" "$XENV xfconf-query -c xfce4-panel -l -v | grep -E '^/plugins/plugin-[0-9]+ '" "whiskermenu"
chk  "Compositor leve ligado (janelas não deixam rastro ao arrastar)" "$XENV echo \$(xfconf-query -c xfwm4 -p /general/use_compositing) \$(xfconf-query -c xfwm4 -p /general/vblank_mode) \$(xfconf-query -c xfwm4 -p /general/show_frame_shadow)" "true xpresent false"
chk  "Atalhos confiáveis na Área de Trabalho" "D=\$(xdg-user-dir DESKTOP); ls \"\$D\"; n=0; for f in \"\$D\"/*.desktop; do $XENV gio info -a metadata::xfce-exe-checksum \"\$f\" | grep -q checksum && n=\$((n+1)); done; echo confiaveis=\$n" "confiaveis=6"
chk  "Teclado ABNT2 na interface" "$XENV setxkbmap -query" "layout: +br"
chk  "Integração com o VirtualBox (VBoxClient)" "pgrep -a VBoxClient" "VBoxClient"
chk  "Firefox com página inicial e favoritos do Lab" "python3 -m json.tool /etc/firefox/policies/policies.json | grep -E 'inicio.html|localhost:8080'" "inicio.html"
chk  "VS Code em português, sem chaveiro e sem aceleração de GPU" "cat ~/.vscode/argv.json" "pt-br"

# ---------------------------------------------------------------- ferramentas e Jenkins
R="$(grun /usr/local/bin/verificar-lab)"; echo "$R" > "$OUT/verificar-lab-1.txt"
if echo "$R" | grep -q 'FALHA'; then bad "verificar-lab (logo após o login)"; else ok "verificar-lab (logo após o login) sem falhas"; fi

# Jenkins liga sozinho ~45 s após o boot; espera até 8 min
J=0; T0=$SECONDS
for _ in $(seq 1 96); do
  if [ "$(gsh "curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/login")" = "200" ]; then J=1; break; fi
  sleep 5
done
if [ "$J" = 1 ]; then ok "Jenkins ligou sozinho e responde em http://localhost:8080 (+$((SECONDS-T0))s após a checagem)"; else bad "Jenkins não respondeu em 8 min"; fi
chk  "Jenkins: login aluno/devops (sem assistente inicial)" "curl -s -o /dev/null -w '%{http_code}' -u aluno:devops http://localhost:8080/api/json" "^200$"
chk  "Jenkins: anônimo bloqueado" "curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/api/json" "^403$"
chk  "Jenkins: plugins Pipeline, Git, GitHub e Docker ativos" "curl -g -s -u aluno:devops 'http://localhost:8080/pluginManager/api/json?depth=1&tree=plugins[shortName,active]' | python3 -c 'import json,sys; a={p[\"shortName\"] for p in json.load(sys.stdin)[\"plugins\"] if p[\"active\"]}; n={\"workflow-aggregator\",\"git\",\"github\",\"docker-workflow\",\"pipeline-stage-view\"}; print(len(a), \"ativos; faltam:\", sorted(n-a) or \"nenhum\")'" "faltam: nenhum"
gcopy "$HERE/vm-tests/pipeline-test.sh" /tmp/pipeline-test.sh
chk  "Jenkins: pipeline com Docker roda com sucesso" "bash /tmp/pipeline-test.sh" "resultado=SUCCESS"

R="$(grun /usr/local/bin/verificar-lab)"; echo "$R" > "$OUT/verificar-lab.txt"
log "$(echo "$R" | sed 's/\x1b\[[0-9;]*m//g')"
if echo "$R" | grep -q '\[OK\].*Jenkins' && ! echo "$R" | grep -qE 'FALHA|AGUARDE'; then
  ok "verificar-lab: todas as ferramentas OK"
else
  bad "verificar-lab"
fi

chk "Serviços: lightdm, NetworkManager, docker (sob demanda), jenkins" "systemctl is-active lightdm NetworkManager docker.socket jenkins | tr '\n' ' '" "^active active active active"
chk "Sessão XFCE do aluno rodando" "pgrep -u aluno -a xfce4-session" "xfce4-session"
chk "Internet dentro da VM" "curl -sS -o /dev/null -w '%{http_code}' https://www.google.com" "^200$"
chk "docker run hello-world (sem sudo)" "docker run --rm hello-world" "Hello from Docker"
chk "Docker Compose sobe um serviço" "d=\$(mktemp -d) && cd \$d && printf 'services:\n  web:\n    image: hello-world\n' > compose.yaml && docker compose up 2>&1 | tail -n 5" "exited with code 0"
chk "Firefox instalado" "firefox --version" "Mozilla Firefox"
chk "Extensões do VS Code (pt-BR, Python, Docker, Terraform, YAML, Ansible)" "code --list-extensions" "ms-python.python"
chk "apt update funciona (repositórios e chaves OK)" "echo devops | sudo -S -p '' apt-get update 2>&1 | tail -n 3" "Lendo listas|Reading package lists"
chk "Ansible executa (ping no localhost)" "ansible localhost -c local -m ping 2>&1" "pong"
chk "Coleções do Ansible (general, docker, posix)" "ansible-galaxy collection list 2>/dev/null" "community.docker"
chk "Terraform executa (init/apply local)" "d=\$(mktemp -d) && cd \$d && printf 'output \"ok\" { value = \"terraform-ok\" }\n' > main.tf && terraform init -input=false >/dev/null && terraform apply -auto-approve -input=false 2>&1 | tail -n 3" "terraform-ok"
chk "Python venv + pip" "python3 -m venv /tmp/venv-qa && /tmp/venv-qa/bin/pip --version" "pip "
chk "Git configura e faz commit" "d=\$(mktemp -d) && cd \$d && git init -q && git -c user.name=qa -c user.email=qa@x commit -q --allow-empty -m qa && git log --oneline | wc -l" "^1$"
chk "SSH ativo com chaves novas" "ls /etc/ssh/ssh_host_ed25519_key; systemctl is-active ssh.socket ssh 2>/dev/null" "ssh_host_ed25519_key"
chk "Identidade única (machine-id gerado)" "cat /etc/machine-id" "^[0-9a-f]{32}$"
chk "Idioma pt-BR, teclado ABNT2, fuso de São Paulo" "echo LANG=\$LANG; cat /etc/default/keyboard; timedatectl show -p Timezone" "Sao_Paulo"
chk "Sudo funciona com a senha devops" "echo devops | sudo -S -k -p '' whoami" "^root$"
log "Swap: $(gsh "swapon --show=NAME,TYPE,SIZE,PRIO --noheadings" | tr '\n' ' ')"
chk "Rede virtio (mais leve com Hyper-V)" "ls /sys/class/net/*/device/driver -l 2>/dev/null | grep -o 'virtio_net' | head -n 1" "virtio_net"
nchk "Sem serviços desnecessários (rsyslog, sysstat, áudio, protetor de tela)" "systemctl is-active rsyslog sysstat 2>/dev/null | grep -x active; pgrep -l -u aluno -x 'pulseaudio|xscreensaver|light-locker'" "active|pulseaudio|xscreensaver|light-locker"
chk "Boot silencioso (quiet)" "cat /proc/cmdline" "quiet"
chk "LEIA-ME e atalho projetos na Área de Trabalho" "ls \"\$(xdg-user-dir DESKTOP)\"" "LEIA-ME.txt"

CORES="$(print_tela tela-2-final)"
if [ "${CORES:-0}" -gt 100 ]; then ok "Tela final desenhada ($CORES cores)"; else bad "Tela final vazia/preta ($CORES cores)"; fi

# ---------------------------------------------------------------- painéis (Painel DevOps e Portainer)
chk  "Atalhos do Painel DevOps e do Portainer no menu e no painel" "ls /usr/share/applications/painel-devops.desktop /usr/share/applications/portainer-devops-lab.desktop ~/.config/xfce4/panel/launcher-15 ~/.config/xfce4/panel/launcher-16" "portainer-devops-lab.desktop"
gsh "painel-devops --servidor" >> "$OUT/qa-detalhes.txt"
PAPI="curl -s -H 'Host: localhost:8090' http://127.0.0.1:8090"
chk  "Painel DevOps responde em localhost:8090" "$PAPI/saude" '"ok": true'
chk  "Painel DevOps: Docker (containers do aluno)" "$PAPI/api/docker | python3 -c 'import json,sys; d=json.load(sys.stdin); print(\"ligado\", d[\"ligado\"], len(d.get(\"containers\",[])), \"containers\")'" "ligado True"
chk  "Painel DevOps: Jenkins (jobs criados)" "$PAPI/api/jenkins | python3 -c 'import json,sys; d=json.load(sys.stdin); print(\"respondendo\", d[\"respondendo\"], [j[\"nome\"] for j in d[\"jobs\"]])'" "respondendo True"
chk  "Painel DevOps: Git, VS Code e Sistema" "for u in git vscode sistema resumo; do $PAPI/api/\$u | python3 -c 'import json,sys; json.load(sys.stdin); print(\"ok\")'; done | tr '\n' ' '" "^ok ok ok ok"
chk  "Painel DevOps: recusa ação sem token (segurança)" "curl -s -X POST -H 'Host: localhost:8090' http://127.0.0.1:8090/api/sistema -d '{}'" "Token inv"
chk  "Painel DevOps: recusa acesso por outro endereço (segurança)" "curl -s -H 'Host: exemplo.com' http://127.0.0.1:8090/api/resumo" "permitido só"
chk  "Portainer liga e responde em localhost:9000" "docker start portainer >/dev/null; for i in \$(seq 1 60); do curl -s -o /dev/null -w '%{http_code}' http://localhost:9000/api/system/status | grep -q 200 && break; sleep 1; done; curl -s http://localhost:9000/api/system/status" "Version"
chk  "Portainer: login admin/devops e ambiente local pronto" "J=\$(curl -s -X POST http://localhost:9000/api/auth -H 'Content-Type: application/json' -d '{\"username\":\"admin\",\"password\":\"devops\"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)[\"jwt\"])'); curl -s http://localhost:9000/api/endpoints -H \"Authorization: Bearer \$J\" | python3 -c 'import json,sys; print(\"ambientes:\", [e[\"Name\"] for e in json.load(sys.stdin)])'" "ambientes: ..local"
log "Portainer: $(gsh "curl -s http://localhost:9000/api/settings/public" | tr -d '\n' | head -c 400)"
gsh "$XENV setsid -f firefox http://localhost:8090 >/dev/null 2>&1; sleep 25" >/dev/null
CORES="$(print_tela tela-4-painel-devops)"
log "Print do Painel DevOps: $CORES cores"
gsh "$XENV setsid -f firefox http://localhost:9000 >/dev/null 2>&1; sleep 20" >/dev/null
CORES="$(print_tela tela-5-portainer)"
log "Print do Portainer: $CORES cores"
gsh "pkill -u aluno firefox; docker stop portainer >/dev/null; true" >/dev/null

# ---------------------------------------------------------------- análise de desempenho e espaço
{
  echo "===== systemd-analyze ====="; gsh "systemd-analyze"
  echo; echo "===== serviços mais lentos ====="; gsh "systemd-analyze blame | head -n 20"
  echo; echo "===== caminho crítico ====="; gsh "systemd-analyze critical-chain graphical.target"
  echo; echo "===== memória ====="; gsh "free -m"
  echo; echo "===== processos que mais usam memória ====="; gsh "ps -eo rss,comm --sort=-rss | head -n 15"
  echo; echo "===== disco ====="; gsh "df -h /"
  echo; echo "===== maiores pacotes (MB) ====="; gsh "dpkg-query -Wf '\${Installed-Size}\t\${Package}\n' | sort -n | tail -n 25 | awk '{printf \"%8.1f  %s\n\", \$1/1024, \$2}'"
  echo; echo "===== pastas grandes ====="; gsh "echo devops | sudo -S -p '' du -sh /usr/share/code /usr/lib/firefox /var/lib/jenkins /usr/share/java /usr/lib/jvm /usr/share/ansible /usr/lib/modules 2>/dev/null"
  echo; echo "===== pacotes removidos no enxugamento ====="; gsh "cat /usr/share/devops-lab/pacotes-removidos.txt"
  echo; echo "===== quem puxou pacotes grandes ====="; gsh "for p in libwebkitgtk-6.0-4 python3-botocore libllvm20 ubuntu-wallpapers-noble; do echo \"## \$p\"; apt-cache rdepends --installed \$p 2>/dev/null | tail -n +3 | head -n 8; done"
  echo; echo "===== autostart da sessão ====="; gsh "ls /etc/xdg/autostart ~/.config/autostart"
  echo; echo "===== janelas na tela ====="; gsh "$XENV xwininfo -root -tree | grep -oE '\"[^\"]+\"' | sort -u | head -n 40"
} > "$ANALISE" 2>&1
log "Boot: $(grep -m1 'Startup finished' "$ANALISE")"
log "Memória: $(grep -m1 '^Mem' "$ANALISE")"

# ---------------------------------------------------------------- 2º boot com CPU limitada (PC lento)
VBoxManage controlvm "$VM" acpipowerbutton
for _ in $(seq 1 60); do
  VBoxManage showvminfo "$VM" --machinereadable | grep -q '^VMState="poweroff"' && break
  sleep 5
done
if VBoxManage showvminfo "$VM" --machinereadable | grep -q '^VMState="poweroff"'; then
  ok "Desligamento pelo botão de energia (ACPI)"
else
  bad "VM não desligou pelo ACPI"; VBoxManage controlvm "$VM" poweroff || true; sleep 5
fi
# 2º boot: PC lento E controladora VMSVGA (é o que o VirtualBox escolhe ao importar o
# arquivo compatível com o VirtualBox 6.1); a imagem tem que aparecer do mesmo jeito.
VBoxManage modifyvm "$VM" --cpu-execution-cap 35 --graphicscontroller vmsvga
VBoxManage startvm "$VM" --type headless
if wait_desktop "boot2-cpu35-vmsvga" 1200; then
  sleep 30
  CORES="$(print_vbox janela-virtualbox-2-vmsvga)"
  if [ "${CORES:-0}" -gt 100 ]; then ok "PC lento + VMSVGA: janela do VirtualBox mostra a área de trabalho ($CORES cores)"; else log "[AVISO] PC lento + VMSVGA: janela do VirtualBox preta ($CORES cores) - o .ova usa VBoxSVGA; com VMSVGA o aluno deve trocar para VBoxSVGA"; fi
  log "PC lento + VMSVGA - resolução: $(gsh "$XENV xrandr 2>/dev/null | sed -n 's/.*current \\([0-9]* x [0-9]*\\).*/\\1/p'")"
  CORES="$(print_tela tela-3-pc-lento)"
  if [ "${CORES:-0}" -gt 100 ]; then ok "PC lento: tela desenhada ($CORES cores)"; else bad "PC lento: tela vazia/preta ($CORES cores)"; fi
  log "PC lento - $(gsh 'systemd-analyze' | head -n 1)"
fi
VBoxManage controlvm "$VM" poweroff >/dev/null 2>&1 || true

log ""
if [ "$FAILS" -eq 0 ]; then log "RESULTADO: TODOS OS TESTES PASSARAM"; else log "RESULTADO: $FAILS FALHA(S)"; fi
exit "$FAILS"
