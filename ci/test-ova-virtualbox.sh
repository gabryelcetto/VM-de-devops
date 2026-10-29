#!/usr/bin/env bash
# Testa o DevOps-Lab-UVV.ova no VirtualBox de verdade (como um aluno faria):
# importa, liga, espera a área de trabalho, testa rede/ferramentas, reinicia
# com a CPU limitada (simula PC lento) e tira prints da tela.
# Uso: ci/test-ova-virtualbox.sh <arquivo.ova> <pasta-de-resultados>
set -uo pipefail

OVA="$1"
OUT="$2"
VM="DevOps-Lab-UVV"
mkdir -p "$OUT"
SUMMARY="$OUT/RESUMO.txt"
FAILS=0

log()  { echo "$*" | tee -a "$SUMMARY"; }
ok()   { log "[OK]    $*"; }
bad()  { log "[FALHA] $*"; FAILS=$((FAILS+1)); }
shot() { VBoxManage controlvm "$VM" screenshotpng "$OUT/$1.png" >/dev/null 2>&1 || true; }
prop() { VBoxManage guestproperty get "$VM" "$1" 2>/dev/null | sed -n 's/^Value: //p'; }
grun() { # executa um comando dentro da VM como aluno
  timeout 300 VBoxManage guestcontrol "$VM" run --username aluno --password devops \
    --wait-stdout --wait-stderr --timeout 240000 -- "$@" 2>&1
}

wait_desktop() { # $1 = rótulo, $2 = limite em segundos
  local label="$1" limit="$2" t=0 users ip
  while [ "$t" -lt "$limit" ]; do
    users="$(prop /VirtualBox/GuestInfo/OS/LoggedInUsers)"
    ip="$(prop /VirtualBox/GuestInfo/Net/0/V4/IP)"
    if [ $((t % 60)) -eq 0 ]; then shot "${label}-${t}s"; fi
    if [ -n "$users" ] && [ "$users" != "0" ] && [ -n "$ip" ]; then
      ok "$label: área de trabalho aberta (usuário logado) e rede com IP $ip em ${t}s"
      sleep 20; shot "${label}-desktop"
      return 0
    fi
    sleep 10; t=$((t+10))
  done
  shot "${label}-timeout"
  bad "$label: não chegou na área de trabalho em ${limit}s (usuários='${users}', ip='${ip}')"
  return 1
}

log "=== Teste do DevOps-Lab-UVV.ova no VirtualBox $(VBoxManage --version) ==="
log "Arquivo: $(basename "$OVA") ($(du -h "$OVA" | cut -f1))"

# ---------------------------------------------------------------- importar
if VBoxManage import "$OVA" --vsys 0 --vmname "$VM" >"$OUT/import.txt" 2>&1; then
  ok "Importação do .ova (Arquivo > Importar Appliance)"
else
  bad "Importação do .ova"; cat "$OUT/import.txt" | tee -a "$SUMMARY"; exit 1
fi
VBoxManage showvminfo "$VM" --machinereadable > "$OUT/vminfo.txt"
grep -E '^(ostype|memory|cpus|graphicscontroller|vram|nic1|storagecontrollertype0|storagecontrollerportcount0|ioapic|paravirtprovider)=' "$OUT/vminfo.txt" | tee -a "$SUMMARY"
# Saída serial para diagnóstico (não muda nada para o aluno)
VBoxManage modifyvm "$VM" --uart1 0x3F8 4 --uartmode1 file "$OUT/serial.log" >/dev/null 2>&1 || true

# ---------------------------------------------------------------- 1º boot
VBoxManage startvm "$VM" --type headless
wait_desktop "boot1" 900

# ---------------------------------------------------------------- testes dentro da VM
if [ -n "$(prop /VirtualBox/GuestAdd/Version)" ]; then
  ok "Guest Additions ativos: $(prop /VirtualBox/GuestAdd/Version)"
else
  bad "Guest Additions não responderam"
fi

sleep 60  # deixa Jenkins/Docker terminarem de subir
R="$(grun /usr/local/bin/verificar-lab)"; echo "$R" > "$OUT/verificar-lab.txt"
if echo "$R" | grep -q '\[OK\].*Jenkins' && ! echo "$R" | grep -q 'FALHA'; then
  ok "verificar-lab: todas as ferramentas OK"
else
  bad "verificar-lab"; echo "$R" | tee -a "$SUMMARY"
fi
log "$(echo "$R" | sed 's/\x1b\[[0-9;]*m//g')"

R="$(grun /usr/bin/systemctl is-active lightdm docker jenkins NetworkManager)"
echo "$R" > "$OUT/servicos.txt"
if [ "$(echo "$R" | grep -c '^active$')" -eq 4 ]; then ok "Serviços ativos: lightdm docker jenkins NetworkManager"; else bad "Serviços: $(echo $R)"; fi

R="$(grun /usr/bin/pgrep -u aluno -a xfce4-session)"
if [ -n "$R" ]; then ok "Sessão XFCE do aluno rodando"; else bad "Sessão XFCE não encontrada"; fi

R="$(grun /usr/bin/curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/login)"
if [ "$R" = "200" ]; then ok "Jenkins responde em http://localhost:8080 (HTTP 200)"; else bad "Jenkins HTTP '$R'"; fi

R="$(grun /usr/bin/curl -sS -o /dev/null -w '%{http_code}' https://www.google.com)"
if [ "$R" = "200" ]; then ok "Internet dentro da VM (https://www.google.com)"; else bad "Internet: '$R'"; fi

R="$(grun /usr/bin/docker run --rm hello-world)"; echo "$R" > "$OUT/docker-hello.txt"
if echo "$R" | grep -q 'Hello from Docker'; then ok "docker run hello-world (sem sudo)"; else bad "docker run hello-world"; log "$R"; fi

R="$(grun /bin/sh -c 'ls /home/aluno/*/LEIA-ME.txt >/dev/null 2>&1 && echo sim')"
if echo "$R" | grep -q sim; then ok "LEIA-ME.txt na Área de Trabalho"; else bad "LEIA-ME.txt não encontrado"; fi

R="$(grun /usr/bin/cat /proc/cmdline)"; log "Kernel cmdline: $R"
echo "$R" | grep -q quiet && ok "Boot silencioso (quiet) configurado" || bad "Boot sem quiet"

R="$(grun /usr/bin/df -h /)"; log "Disco: $(echo "$R" | tail -1)"
shot "boot1-final"

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
VBoxManage modifyvm "$VM" --cpu-execution-cap 35
VBoxManage startvm "$VM" --type headless
wait_desktop "boot2-cpu35" 1200
VBoxManage controlvm "$VM" poweroff >/dev/null 2>&1 || true

log ""
if [ "$FAILS" -eq 0 ]; then log "RESULTADO: TODOS OS TESTES PASSARAM"; else log "RESULTADO: $FAILS FALHA(S)"; fi
exit "$FAILS"
