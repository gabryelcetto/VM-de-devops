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
# Com janela (como o aluno usa) quando há um X (Xvfb no CI): a tela preta da VMSVGA só
# aparecia com janela; em "headless" o teste passava e o defeito chegava ao aluno.
TIPO="${VBOX_TIPO:-headless}"; [ -n "${DISPLAY:-}" ] || TIPO=headless
log "Modo do VirtualBox no teste: $TIPO"
VBoxManage setextradata global GUI/SuppressMessages "all" >/dev/null 2>&1 || true
VBoxManage startvm "$VM" --type "$TIPO"
wait_desktop "boot1" 900
sleep 20

if [ -n "$(prop /VirtualBox/GuestAdd/Version)" ]; then
  ok "Guest Additions ativos: $(prop /VirtualBox/GuestAdd/Version)"
else
  bad "Guest Additions não responderam"
fi

# Ferramentas de print/inspeção da tela, só para o teste (esta VM é descartada depois)
gsh "echo devops | sudo -S -p '' apt-get update -qq; echo devops | sudo -S -p '' apt-get install -y -qq x11-utils x11-apps xdotool >/dev/null; which xwd xwininfo xdotool" >> "$OUT/qa-detalhes.txt"

# ---------------------------------------------------------------- imagem na janela do VirtualBox
# (sem redimensionar nada: é exatamente o que o aluno vê ao ligar a VM)
CORES="$(print_vbox janela-virtualbox-1)"
if [ "${CORES:-0}" -gt 100 ]; then ok "Janela do VirtualBox mostra a área de trabalho ($CORES cores)"; else bad "Janela do VirtualBox PRETA após o login ($CORES cores)"; fi

# ---------------------------------------------------------------- mouse e janela (só com janela)
if [ "$TIPO" = gui ] && command -v xdotool >/dev/null; then
  W="$(xdotool search --name "^$VM" 2>/dev/null | tail -n 1)"
  read -r WX WY WL WA < <(xdotool getwindowgeometry --shell "$W" 2>/dev/null | awk -F= '/^X=/{x=$2}/^Y=/{y=$2}/^WIDTH=/{l=$2}/^HEIGHT=/{a=$2}END{print x+0, y+0, l+0, a+0}')
  MOK=0; MTXT=""
  for pos in "0.25 0.40" "0.70 0.65"; do
    read -r fx fy <<<"$pos"
    hx=$(awk -v a="$WX" -v l="$WL" -v f="$fx" 'BEGIN{print int(a+l*f)}'); hy=$(awk -v a="$WY" -v l="$WA" -v f="$fy" 'BEGIN{print int(a+l*f)}')
    xdotool mousemove "$hx" "$hy"; sleep 0.5; xdotool mousemove_relative 1 1; sleep 1.5
    G="$(gsh "$XENV xdotool getmouselocation")"
    gx=$(echo "$G" | sed -n 's/.*x:\([0-9]*\).*/\1/p'); gy=$(echo "$G" | sed -n 's/.*y:\([0-9]*\).*/\1/p')
    # o ponteiro dentro da VM vai para o mesmo ponto da janela (descontando a barra de menu)
    dx=$(( ${gx:-9999} - (hx + 1 - WX) )); dy=$(( ${gy:-9999} - (hy + 1 - WY) ))
    [ "${dx#-}" -le 40 ] && [ "${dy#-}" -le 70 ] && MOK=$((MOK+1))
    MTXT="$MTXT computador($hx,$hy)->VM(${gx:-?},${gy:-?})"
  done
  if [ "$MOK" = 2 ]; then ok "Integração do mouse: o ponteiro da VM segue o mouse do computador sem capturar ($MTXT)"; else bad "Integração do mouse: o ponteiro da VM não seguiu o mouse ($MTXT; janela $WX,$WY ${WL}x$WA)"; fi
fi
for res in "1366 768" "1280 800"; do
  # shellcheck disable=SC2086
  VBoxManage controlvm "$VM" setvideomodehint $res 32 >/dev/null 2>&1; sleep 12
  CORES="$(print_vbox "janela-redimensionada-${res// /x}")"; ATUAL="$(gsh "$XENV xrandr --current | sed -n 's/.*current \\([0-9]*\\) x \\([0-9]*\\).*/\\1x\\2/p'")"
  if [ "$ATUAL" = "${res// /x}" ] && [ "${CORES:-0}" -gt 100 ]; then ok "Janela redimensionada para ${res// /x}: a tela da VM acompanha e não fica preta"; else bad "Janela redimensionada para ${res// /x}: resolução '$ATUAL', $CORES cores"; fi
done

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
chk  "Atalhos confiáveis na Área de Trabalho" "D=\$(xdg-user-dir DESKTOP); ls \"\$D\"; n=0; for f in \"\$D\"/*.desktop; do $XENV gio info -a metadata::xfce-exe-checksum \"\$f\" | grep -q checksum && n=\$((n+1)); done; echo confiaveis=\$n" "confiaveis=8"
chk  "Teclado ABNT2 na interface" "$XENV setxkbmap -query" "layout: +br"
chk  "Integração com o VirtualBox: copiar/colar e ajuste de tela ligados, arrastar/soltar desligado (leve)" "pgrep -a VBoxClient; echo clipboard=\$(pgrep -fc 'VBoxClient [-]-clipboard') tela=\$(pgrep -fc 'VBoxClient [-]-vmsvga') arrastar=\$(pgrep -fc 'VBoxClient [-]-draganddrop')" "clipboard=[1-9] tela=[1-9] arrastar=0"
# (antes de qualquer teste baixar imagens: confere que vieram dentro do .ova)
chk  "Imagens Docker já baixadas (nginx, python, alpine, hello-world)" "docker image inspect nginx:alpine python:3.12-slim alpine:latest hello-world:latest --format '{{.Id}}' | wc -l" "^4$"
chk  "Imagens do monitoramento guardadas na VM (compactadas, íntegras)" "ls -la /opt/devops-lab/monitoramento/imagens.tar.zst && zstd -tq --long=27 /opt/devops-lab/monitoramento/imagens.tar.zst && echo integro" "integro"
chk  "Docker guarda as imagens no overlay2 (sem cópia dupla do containerd)" "docker info --format '{{.Driver}}'" "^overlay2$"
chk  "Monitoramento vem desligado (não gasta memória no boot)" "docker ps --filter label=com.docker.compose.project=monitoramento --format '{{.Names}}' | wc -l" "^0$"
chk  "Firefox com página inicial e favoritos do Lab" "python3 -m json.tool /etc/firefox/policies/policies.json | grep -E 'inicio.html|localhost:8080'" "inicio.html"
chk  "VS Code em português, sem chaveiro e sem aceleração de GPU" "cat ~/.vscode/argv.json" "pt-br"
nchk "Sem peso morto no .ova (cache de .vsix e Copilot embutido, que fica desligado)" "ls -d ~/.config/Code/CachedExtensionVSIXs /usr/share/code/resources/app/extensions/copilot 2>/dev/null" "CachedExtensionVSIXs|copilot"

# ---------------------------------------------------------------- ferramentas e Jenkins
R="$(grun /usr/local/bin/verificar-lab)"; echo "$R" > "$OUT/verificar-lab-1.txt"
if echo "$R" | grep -q 'FALHA'; then bad "verificar-lab (logo após o login)"; else ok "verificar-lab (logo após o login) sem falhas"; fi

# ---------------------------------------------------------------- leveza (VM parada, como o aluno deixa)
# Mede por dentro da VM sem o guestcontrol ativo (ele mesmo gasta CPU) e, junto, a CPU do
# VirtualBox no computador: é o que pesa no VirtualBox com Hyper-V (tartaruga verde).
# (a atualização da lista do apt roda sozinha 3 min após o boot: roda agora para não cair na medida)
gsh "echo devops | sudo -S -p '' systemctl start devops-lab-apt-update.service" >/dev/null
gcopy "$HERE/vm-tests/medir-ocioso.sh" /tmp/medir-ocioso.sh
gsh "setsid -f bash /tmp/medir-ocioso.sh 20 30 /tmp/medida.txt >/dev/null 2>&1 < /dev/null" >/dev/null
VMPID="$(pgrep -f "VirtualBoxVM.*$VM|VBoxHeadless.*$VM" | head -n 1)"
sleep 20; H1=$(awk '{print $14+$15}' "/proc/$VMPID/stat" 2>/dev/null || echo 0); sleep 30; H2=$(awk '{print $14+$15}' "/proc/$VMPID/stat" 2>/dev/null || echo 0)
for _ in $(seq 1 20); do gsh "test -e /tmp/medida.txt.ok && echo pronto" | grep -q pronto && break; sleep 2; done
M="$(gsh "cat /tmp/medida.txt")"; printf '### VM parada\n%s\n\n' "$M" >> "$OUT/qa-detalhes.txt"
HOSTCPU=$(( (H2 - H1) * 100 / $(getconf CLK_TCK) / 30 ))
GCPU="$(echo "$M" | sed -n 's/^CPU ocupada.*: \([0-9]*\).*/\1/p')"
TICS="$(echo "$M" | awk '$2=="LOC"{print $1; exit}')"
log "VM parada: VirtualBox no computador ${HOSTCPU}% de 1 núcleo | dentro da VM ${GCPU:-?}% | relógio ${TICS:-?}/s"
# Limites: não pode pesar mais que a versão anterior (14% no computador, medido) e a VM
# parada tem que ficar abaixo de 8%. O relógio (interrupções/s) fica só anotado: varia
# com o computador e o que importa para o aluno é a CPU gasta.
if [ "$HOSTCPU" -le 14 ] && [ "${GCPU:-99}" -le 8 ]; then ok "VM parada é leve (computador ${HOSTCPU}%, VM ${GCPU}%, relógio ${TICS:-?}/s)"; else bad "VM parada pesada: computador ${HOSTCPU}% (máx 14), VM ${GCPU:-?}% (máx 8), relógio ${TICS:-?}/s"; log "$(echo "$M" | sed -n '3,12p')"; fi

# Jenkins fica DESLIGADO até o aluno usar (VM leve no começo); o atalho "Jenkins" liga e abre
sleep 30
chk  "Jenkins não liga sozinho no boot (fica leve até usar)" "awk '{print int(\$1)\"s de boot\"}' /proc/uptime; echo \$(systemctl is-active jenkins) \$(systemctl is-enabled jenkins)" "inactive disabled"
gsh "mkdir -p /tmp/ff && printf '#!/bin/sh\\necho ABRIU \$*\\n' > /tmp/ff/firefox && chmod +x /tmp/ff/firefox; (PATH=/tmp/ff:\$PATH setsid -f abrir-jenkins > /tmp/abrir-jenkins.txt 2>&1)" >/dev/null
J=0; T0=$SECONDS
for _ in $(seq 1 96); do
  if [ "$(gsh "curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/login")" = "200" ]; then J=1; break; fi
  sleep 5
done
if [ "$J" = 1 ]; then ok "Atalho Jenkins liga o Jenkins e ele responde em http://localhost:8080 (em $((SECONDS-T0))s)"; else bad "Jenkins não respondeu em 8 min depois do atalho"; fi
sleep 5
chk  "Atalho Jenkins abre o Firefox no Jenkins quando ele fica pronto" "cat /tmp/abrir-jenkins.txt" "ABRIU http://localhost:8080"
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
chk "Extensões do VS Code (pt-BR, Python, Docker, Terraform, YAML)" "code --list-extensions" "ms-python.python"
chk "apt update funciona (repositórios e chaves OK)" "echo devops | sudo -S -p '' apt-get update 2>&1 | tail -n 3" "Lendo listas|Reading package lists"
nchk "Ansible não vem mais na VM" "command -v ansible ansible-playbook" "ansible"
chk "Terraform executa (init/apply local)" "d=\$(mktemp -d) && cd \$d && printf 'output \"ok\" { value = \"terraform-ok\" }\n' > main.tf && terraform init -input=false >/dev/null && terraform apply -auto-approve -input=false 2>&1 | tail -n 3" "terraform-ok"
chk "Python venv + pip" "python3 -m venv /tmp/venv-qa && /tmp/venv-qa/bin/pip --version" "pip "
chk "Git configura e faz commit" "d=\$(mktemp -d) && cd \$d && git init -q && git -c user.name=qa -c user.email=qa@x commit -q --allow-empty -m qa && git log --oneline | wc -l" "^1$"
chk "SSH ativo com chaves novas" "ls /etc/ssh/ssh_host_ed25519_key; systemctl is-active ssh.socket ssh 2>/dev/null" "ssh_host_ed25519_key"
chk "Identidade única (machine-id gerado)" "cat /etc/machine-id" "^[0-9a-f]{32}$"
chk "Idioma pt-BR, teclado ABNT2, fuso de São Paulo" "echo LANG=\$LANG; cat /etc/default/keyboard; timedatectl show -p Timezone" "Sao_Paulo"
chk "Sudo funciona com a senha devops" "echo devops | sudo -S -k -p '' whoami" "^root$"
log "Swap: $(gsh "swapon --show=NAME,TYPE,SIZE,PRIO --noheadings" | tr '\n' ' ')"
chk "Memória comprimida (zswap) ligada" "echo \$(cat /sys/module/zswap/parameters/enabled) \$(cat /sys/module/zswap/parameters/compressor) \$(cat /sys/module/zswap/parameters/zpool)" "^Y "
log "zswap: $(gsh "echo \$(cat /sys/module/zswap/parameters/compressor) \$(cat /sys/module/zswap/parameters/zpool) max=\$(cat /sys/module/zswap/parameters/max_pool_percent)%")"
chk "earlyoom protege contra travamento por falta de memória" "systemctl is-active earlyoom; ps -o args= -C earlyoom" "prefer"
chk "Jenkins é o último a ser fechado se faltar memória" "cat /proc/\$(systemctl show -p MainPID --value jenkins)/oom_score_adj" "^-300$"
chk "VS Code e Firefox com ajustes de desempenho" "echo vscode=\$(grep -c watcherExclude ~/.config/Code/User/settings.json) firefox=\$(grep -c processCount /etc/firefox/policies/policies.json)" "vscode=1 firefox=1"
chk "Rede virtio (mais leve com Hyper-V)" "ls /sys/class/net/*/device/driver -l 2>/dev/null | grep -o 'virtio_net' | head -n 1" "virtio_net"
nchk "Sem serviços desnecessários (rsyslog, sysstat, áudio, protetor de tela)" "systemctl is-active rsyslog sysstat 2>/dev/null | grep -x active; pgrep -l -u aluno -x 'pulseaudio|xscreensaver|light-locker'" "active|pulseaudio|xscreensaver|light-locker"
chk "Boot silencioso (quiet)" "cat /proc/cmdline" "quiet"
chk "LEIA-ME e atalho projetos na Área de Trabalho" "ls \"\$(xdg-user-dir DESKTOP)\"" "LEIA-ME.txt"

CORES="$(print_tela tela-2-final)"
if [ "${CORES:-0}" -gt 100 ]; then ok "Tela final desenhada ($CORES cores)"; else bad "Tela final vazia/preta ($CORES cores)"; fi

# ---------------------------------------------------------------- Painel DevOps (painel visual único)
chk  "Atalho do Painel DevOps na área de trabalho, no menu e no painel" "ls /usr/share/applications/painel-devops.desktop ~/.config/xfce4/panel/launcher-15; grep -c painel-devops ~/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml" "painel-devops.desktop"
chk  "Painel DevOps já está no ar depois do login (favorito do Firefox funciona sem abrir o ícone)" "curl -s -H 'Host: localhost:8090' http://127.0.0.1:8090/saude" '"ok": true'
chk  "Firefox tem o favorito do Painel DevOps" "grep -c 'localhost:8090' /etc/firefox/policies/policies.json" "^[1-9]"
gsh "painel-devops --servidor" >> "$OUT/qa-detalhes.txt"
PAPI="curl -s -H 'Host: localhost:8090' http://127.0.0.1:8090"
PTOK="T=\$($PAPI/ | sed -n 's/.*name=\"painel-token\" content=\"\\([^\"]*\\)\".*/\\1/p');"
PPOST="curl -s -X POST -H 'Host: localhost:8090' -H \"X-Painel-Token: \$T\" -H 'Content-Type: application/json' http://127.0.0.1:8090"
chk  "Painel DevOps responde em localhost:8090" "$PAPI/saude" '"ok": true'
for a in docker jenkins git vscode terraform python monitoramento sistema resumo tarefas ferramentas; do
  chk "Painel DevOps: aba $a carrega" "$PAPI/api/$a | python3 -c 'import json,sys; d=json.load(sys.stdin); print(\"ok\" if \"erro\" not in d else d)'" "^ok$"
done
chk  "Painel DevOps: Docker ligado e Jenkins respondendo" "$PAPI/api/resumo | python3 -c 'import json,sys; d=json.load(sys.stdin); print(\"docker\", d[\"docker\"][\"ligado\"], \"jenkins\", d[\"jenkins\"][\"respondendo\"])'" "docker True jenkins True"
chk  "Painel DevOps: todas as ferramentas instaladas" "$PAPI/api/ferramentas | python3 -c 'import json,sys; f=json.load(sys.stdin)[\"ferramentas\"]; print(len(f), \"falhando:\", [x[\"nome\"] for x in f if not x[\"ok\"]] or \"nenhuma\")'" "falhando: nenhuma"
chk  "Painel DevOps: cria container pelo botão (modelo + limite de 256 MB)" "$PTOK $PPOST/api/docker -d '{\"acao\":\"run\",\"imagem\":\"nginx:alpine\",\"nome\":\"painel-web\",\"portas\":\"8091:80\",\"memoria\":\"256m\"}'; sleep 3; curl -s -o /dev/null -w 'http=%{http_code} ' http://localhost:8091; docker inspect -f 'mem={{.HostConfig.Memory}}' painel-web" "http=200 mem=268435456"
chk  "Painel DevOps: cria projeto Compose e sobe com saída ao vivo" "$PTOK $PPOST/api/arquivo -d '{\"acao\":\"projeto\",\"nome\":\"qa-compose\",\"arquivos\":{\"docker-compose.yml\":\"services:\\n  web:\\n    image: nginx:alpine\\n    ports:\\n      - \\\"8092:80\\\"\\n    mem_limit: 1g\\n\"}}' >/dev/null; I=\$($PPOST/api/executar -d '{\"ferramenta\":\"docker\",\"acao\":\"compose_up\",\"arquivo\":\"~/projetos/qa-compose/docker-compose.yml\"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)[\"resultado\"][\"tarefa\"])'); for i in \$(seq 1 60); do $PAPI/api/tarefa?id=\$I | grep -q '\"fim\": true' && break; sleep 2; done; $PAPI/api/tarefa?id=\$I | python3 -c 'import json,sys; t=json.load(sys.stdin); print(\"codigo\", t[\"codigo\"])'; curl -s -o /dev/null -w 'http=%{http_code}' http://localhost:8092" "http=200"
chk  "Painel DevOps: cria Freestyle numa Pasta e roda com sucesso" "$PTOK $PPOST/api/jenkins -d '{\"acao\":\"criar\",\"tipo\":\"pasta\",\"job\":\"qa-pasta\"}' >/dev/null; $PPOST/api/jenkins -d '{\"acao\":\"criar\",\"tipo\":\"freestyle\",\"job\":\"qa-free\",\"pasta\":\"qa-pasta\",\"comandos\":\"echo qa-ok\"}' >/dev/null; $PPOST/api/jenkins -d '{\"acao\":\"construir\",\"job\":\"qa-pasta/qa-free\"}' >/dev/null; for i in \$(seq 1 40); do $PPOST/api/jenkins -d '{\"acao\":\"console\",\"job\":\"qa-pasta/qa-free\"}' | grep -q 'Finished: SUCCESS' && break; sleep 3; done; $PPOST/api/jenkins -d '{\"acao\":\"console\",\"job\":\"qa-pasta/qa-free\"}' | grep -o 'Finished: SUCCESS'; $PPOST/api/jenkins -d '{\"acao\":\"apagar\",\"job\":\"qa-pasta\"}' >/dev/null" "Finished: SUCCESS"
chk  "Painel DevOps: gera chave SSH do Git" "$PTOK $PPOST/api/git -d '{\"acao\":\"gerar_chave\",\"email\":\"qa@devops-lab\"}' >/dev/null; $PAPI/api/git | python3 -c 'import json,sys; print(json.load(sys.stdin)[\"chave\"].get(\"publica\",\"\")[:11])'; rm -f ~/.ssh/id_ed25519 ~/.ssh/id_ed25519.pub" "ssh-ed25519"
chk  "GitHub conhecido para SSH (sem pergunta de confiança)" "ssh-keygen -F github.com -f /etc/ssh/ssh_known_hosts | grep -c github.com" "^[1-9]"
chk  "Painel DevOps: recusa ação sem token (segurança)" "curl -s -X POST -H 'Host: localhost:8090' http://127.0.0.1:8090/api/sistema -d '{}'" "Token inv"
chk  "Painel DevOps: recusa acesso por outro endereço (segurança)" "curl -s -H 'Host: exemplo.com' http://127.0.0.1:8090/api/resumo" "permitido só"
# espera uma tarefa do Painel (saída ao vivo) terminar e mostra o código de saída
PTAREFA="python3 -c 'import json,sys; print(json.load(sys.stdin)[\"resultado\"][\"tarefa\"])'"
PESPERA="for i in \$(seq 1 120); do $PAPI/api/tarefa?id=\$I | grep -q '\"fim\": true' && break; sleep 2; done; $PAPI/api/tarefa?id=\$I | python3 -c 'import json,sys; t=json.load(sys.stdin); print(\"codigo\", t[\"codigo\"])';"
PMON="$PAPI/api/monitoramento | python3 -c 'import json,sys; print(\" \".join(x[\"id\"]+\"=\"+(\"no-ar\" if x[\"no_ar\"] else \"fora\") for x in json.load(sys.stdin)[\"servicos\"]))'"
chk  "Painel DevOps: Ligar monitoramento sobe Grafana, Uptime Kuma, Prometheus e node-exporter" "$PTOK I=\$($PPOST/api/executar -d '{\"ferramenta\":\"monitoramento\",\"acao\":\"ligar\"}' | $PTAREFA); $PESPERA for i in \$(seq 1 60); do $PMON | grep -q fora || break; sleep 3; done; $PMON" "grafana=no-ar uptime-kuma=no-ar prometheus=no-ar node-exporter=no-ar"
chk  "Imagens do monitoramento carregadas no primeiro Ligar (Grafana, Uptime Kuma, Prometheus, node-exporter)" "cd /opt/devops-lab/monitoramento && docker compose config --images | xargs docker image inspect --format '{{.Id}}' | wc -l" "^4$"
chk  "Grafana: login aluno/devops e fonte Prometheus funcionando" "curl -s -u aluno:devops http://127.0.0.1:3000/api/datasources/uid/prometheus/health" '"status":"OK"'
chk  "Grafana: painel Esta VM com dados da VM" "for i in \$(seq 1 30); do curl -s -u aluno:devops 'http://127.0.0.1:3000/api/datasources/proxy/uid/prometheus/api/v1/query?query=node_memory_MemTotal_bytes' | grep -q '\"result\":\[{' && break; sleep 3; done; echo \$(curl -s -u aluno:devops http://127.0.0.1:3000/api/dashboards/uid/esta-vm | grep -o 'Esta VM' | head -n 1; curl -s -u aluno:devops 'http://127.0.0.1:3000/api/datasources/proxy/uid/prometheus/api/v1/query?query=node_memory_MemTotal_bytes' | grep -o '\"result\":\[{' | head -n 1)" 'Esta VM "result"'
chk  "Prometheus coleta a VM, o Docker e ele mesmo" "for i in \$(seq 1 30); do curl -s 'http://127.0.0.1:9090/api/v1/query?query=up' | grep -q '\"esta-vm\"' && break; sleep 3; done; sleep 16; curl -s 'http://127.0.0.1:9090/api/v1/query?query=up' | python3 -c 'import json,sys; print(sorted((r[\"metric\"][\"job\"], r[\"value\"][1]) for r in json.load(sys.stdin)[\"data\"][\"result\"]))'" "\('docker', '1'\), \('esta-vm', '1'\), \('prometheus', '1'\)"
chk  "Uptime Kuma responde em localhost:3001" "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3001/" "^(200|302)$"
{ echo "===== memória do monitoramento ligado ====="; gsh "docker stats --no-stream --format '{{.Name}} {{.MemUsage}}'; free -m"; } >> "$OUT/qa-detalhes.txt" 2>&1
# Fecha o Firefox e ESPERA ele sair de verdade: abrir outro enquanto o anterior ainda está
# fechando faz o pedido cair no Firefox que está saindo (janela em branco ou nenhuma janela)
FECHA_FF="pkill -u aluno firefox; for i in \$(seq 1 30); do pgrep -u aluno firefox >/dev/null || break; sleep 1; done; pkill -9 -u aluno firefox; sleep 1; true"
janela() { # $1 = regex do título da janela; espera até 45 s; sem janela, mostra o que tinha (diagnóstico)
  gsh "$XENV for i in \$(seq 1 45); do xwininfo -root -tree | grep -E '$1' && exit 0; sleep 1; done; echo sem-janela; xwininfo -root -tree | grep -i -E 'firefox|nova aba|new tab'; pgrep -a -u aluno firefox; tail -n 15 ~/.cache/painel-devops.log"
}
gsh "$FECHA_FF" >/dev/null
gsh "$XENV setsid -f firefox http://localhost:3000 >/dev/null 2>&1; sleep 25" >/dev/null
print_tela tela-5-grafana >/dev/null
gsh "$FECHA_FF" >/dev/null
chk  "Painel DevOps: Desligar monitoramento libera a memória (dados ficam guardados)" "$PTOK I=\$($PPOST/api/executar -d '{\"ferramenta\":\"monitoramento\",\"acao\":\"desligar\"}' | $PTAREFA); $PESPERA $PMON; docker volume ls --format '{{.Name}}' | grep -c 'monitoramento_'" "grafana=fora uptime-kuma=fora prometheus=fora node-exporter=fora"
chk  "Atalhos Grafana e Uptime Kuma na área de trabalho e no menu" "D=\$(xdg-user-dir DESKTOP); ls \"\$D\"/grafana-devops-lab.desktop \"\$D\"/uptime-kuma-devops-lab.desktop /usr/share/applications/prometheus-devops-lab.desktop | wc -l" "^3$"
chk  "Atalho Grafana liga o monitoramento desligado e abre o Firefox" "mkdir -p /tmp/ff && printf '#!/bin/sh\\necho ABRIU \$*\\n' > /tmp/ff/firefox && chmod +x /tmp/ff/firefox && PATH=/tmp/ff:\$PATH timeout 300 abrir-monitoramento grafana 2>&1 | tail -n 1; cd /opt/devops-lab/monitoramento && docker compose down >/dev/null 2>&1" "ABRIU http://localhost:3000"
chk  "Atalho Docker abre a tela do Docker (estilo do app) numa janela própria" "D=\$(xdg-user-dir DESKTOP); grep -h '^Exec=' \"\$D\"/docker-devops-lab.desktop; PATH=/tmp/ff:\$PATH painel-devops docker" "ABRIU (--new-window )?http://localhost:8090/\\?app=docker#docker"
gsh "$FECHA_FF" >/dev/null
gsh "$XENV setsid -f painel-devops docker >/dev/null 2>&1" >/dev/null
R="$(janela '"Docker \(DevOps-Lab\)')"; sleep 5
print_tela tela-6-docker-app >/dev/null
printf '### Janela do atalho Docker\n%s\n\n' "$R" >> "$OUT/qa-detalhes.txt"
if echo "$R" | grep -q '"Docker (DevOps-Lab)'; then ok "Atalho Docker de verdade: abre a janela \"Docker (DevOps-Lab)\" no Firefox"; else bad "Atalho Docker de verdade: a janela do Docker não abriu"; log "$(echo "$R" | tail -n 8)"; fi
chk  "Atalho Docker de verdade: a tela do Docker busca os containers" "awk '/GET \\/\\?app=docker/{a=1} a && /GET \\/api\\/docker/{print \"tela-carregou\"; exit}' ~/.cache/painel-devops.log" "tela-carregou"
gsh "$FECHA_FF" >/dev/null
chk  "Painel DevOps: Apagar projeto Terraform roda o destroy antes de apagar a pasta" "$PTOK $PPOST/api/arquivo -d '{\"acao\":\"projeto\",\"nome\":\"qa-tf\",\"arquivos\":{\"main.tf\":\"resource \\\"terraform_data\\\" \\\"x\\\" {\\n  input = \\\"qa\\\"\\n}\\n\"}}' >/dev/null; for a in init apply; do I=\$($PPOST/api/executar -d '{\"ferramenta\":\"terraform\",\"acao\":\"'\$a'\",\"pasta\":\"~/projetos/qa-tf\"}' | $PTAREFA); $PESPERA done; I=\$($PPOST/api/executar -d '{\"ferramenta\":\"projeto\",\"acao\":\"apagar\",\"pasta\":\"~/projetos/qa-tf\"}' | $PTAREFA); $PESPERA D=\$($PAPI/api/tarefa?id=\$I | grep -o 'Destroy complete' | head -n 1); test -e ~/projetos/qa-tf && P=pasta-ficou || P=pasta-apagada; echo \"\$D \$P\"" "Destroy complete pasta-apagada"
gsh "$XENV setsid -f firefox http://localhost:8090 >/dev/null 2>&1" >/dev/null
R="$(janela '"Painel DevOps ')"; sleep 5
CORES="$(print_tela tela-4-painel-devops)"
printf '### Janela do Painel DevOps\n%s\n\n' "$R" >> "$OUT/qa-detalhes.txt"
# Só cores não basta: a área de trabalho sozinha já é colorida. Tem que ter a janela com o título do painel.
if echo "$R" | grep -q '"Painel DevOps ' && [ "${CORES:-0}" -gt 100 ]; then ok "Painel DevOps aberto no Firefox ($CORES cores)"; else bad "Painel DevOps não apareceu no Firefox ($CORES cores)"; log "$(echo "$R" | tail -n 8)"; fi
# Com o Firefox já aberto (no Painel), o atalho Docker abre outra janela, a do Docker
gsh "$XENV setsid -f painel-devops docker >/dev/null 2>&1" >/dev/null
R="$(janela '"Docker \(DevOps-Lab\)')"
printf '### Atalho Docker com o Firefox já aberto\n%s\n\n' "$R" >> "$OUT/qa-detalhes.txt"
if echo "$R" | grep -q '"Docker (DevOps-Lab)'; then ok "Atalho Docker com o Firefox já aberto: abre a janela do Docker"; else bad "Atalho Docker com o Firefox já aberto: a janela do Docker não abriu"; log "$(echo "$R" | tail -n 8)"; fi
gsh "$FECHA_FF; docker rm -f painel-web >/dev/null; cd ~/projetos/qa-compose && docker compose down >/dev/null 2>&1; rm -rf ~/projetos/qa-compose; true" >/dev/null

# ---------------------------------------------------------------- análise de desempenho e espaço
{
  echo "===== systemd-analyze ====="; gsh "systemd-analyze"
  echo; echo "===== serviços mais lentos ====="; gsh "systemd-analyze blame | head -n 20"
  echo; echo "===== caminho crítico ====="; gsh "systemd-analyze critical-chain graphical.target"
  echo; echo "===== memória ====="; gsh "free -m"
  echo; echo "===== processos que mais usam memória ====="; gsh "ps -eo rss,comm --sort=-rss | head -n 15"
  echo; echo "===== disco ====="; gsh "df -h /"
  echo; echo "===== maiores pacotes (MB) ====="; gsh "dpkg-query -Wf '\${Installed-Size}\t\${Package}\n' | sort -n | tail -n 25 | awk '{printf \"%8.1f  %s\n\", \$1/1024, \$2}'"
  echo; echo "===== pastas grandes ====="; gsh "echo devops | sudo -S -p '' du -sh /usr/share/code /usr/lib/firefox /var/lib/jenkins /usr/share/java /usr/lib/jvm /usr/lib/modules /var/lib/docker /var/lib/containerd /opt 2>/dev/null"
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
# 2º boot: PC lento (CPU limitada, como o VirtualBox com Hyper-V) E a outra controladora
# (VBoxSVGA, se o aluno trocar nas configurações): a imagem tem que aparecer do mesmo jeito.
VBoxManage modifyvm "$VM" --cpu-execution-cap 35 --graphicscontroller vboxsvga
# as propriedades do 1º boot ficam guardadas: apaga para esperar o login de verdade
VBoxManage guestproperty unset "$VM" /VirtualBox/GuestInfo/OS/LoggedInUsers >/dev/null 2>&1 || true
VBoxManage guestproperty unset "$VM" /VirtualBox/GuestInfo/Net/0/V4/IP >/dev/null 2>&1 || true
VBoxManage startvm "$VM" --type "$TIPO"
if wait_desktop "boot2-cpu35-vboxsvga" 1200; then
  # com a CPU limitada a tela leva um pouco mais para aparecer: espera até 2 min
  T=0; CORES=0
  while [ "$T" -lt 120 ]; do
    CORES="$(print_vbox janela-virtualbox-2-vboxsvga)"
    [ "${CORES:-0}" -gt 100 ] && break
    sleep 5; T=$((T+5))
  done
  if [ "${CORES:-0}" -gt 100 ]; then ok "PC lento + VBoxSVGA: janela do VirtualBox mostra a área de trabalho ($CORES cores, ${T}s depois do login)"; else bad "PC lento + VBoxSVGA: janela do VirtualBox preta 2 min depois do login ($CORES cores)"; fi
  log "PC lento + VBoxSVGA - resolução: $(gsh "$XENV xrandr 2>/dev/null | sed -n 's/.*current \\([0-9]* x [0-9]*\\).*/\\1/p'")"
  CORES="$(print_tela tela-3-pc-lento)"
  if [ "${CORES:-0}" -gt 100 ]; then ok "PC lento: tela desenhada ($CORES cores)"; else bad "PC lento: tela vazia/preta ($CORES cores)"; fi
  log "PC lento - $(gsh 'systemd-analyze' | head -n 1)"
fi
VBoxManage controlvm "$VM" poweroff >/dev/null 2>&1 || true

log ""
if [ "$FAILS" -eq 0 ]; then log "RESULTADO: TODOS OS TESTES PASSARAM"; else log "RESULTADO: $FAILS FALHA(S)"; fi
exit "$FAILS"
