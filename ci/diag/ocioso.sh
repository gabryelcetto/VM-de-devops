#!/usr/bin/env bash
# Por que a VM parada acorda tanto? Liga o .ova final (VMSVGA) com janela, repete a
# sequência do teste até a medida "VM parada" e mede de novo mudando uma coisa de cada vez.
# Em cada passo: CPU do VirtualBox no computador, CPU dentro da VM, interrupções e
# quais timers do kernel disparam (ftrace).
# Uso: ci/diag/ocioso.sh <arquivo.ova> <pasta>
set -uo pipefail
OVA="$1"; OUT="$2"; VM="DevOps-Lab"; HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT"; R="$OUT/RESUMO-ocioso.txt"
log()  { echo "$*" | tee -a "$R"; }
prop() { VBoxManage guestproperty get "$VM" "$1" 2>/dev/null | sed -n 's/^Value: //p'; }
gsh()  { timeout 300 VBoxManage guestcontrol "$VM" run --username aluno --password devops \
  --wait-stdout --wait-stderr --timeout 280000 -- /bin/bash -lc "$1" 2>&1; }
gcopy_to()   { VBoxManage guestcontrol "$VM" copyto --username aluno --password devops "$1" "$2" >/dev/null 2>&1; }
gcopy_from() { VBoxManage guestcontrol "$VM" copyfrom --username aluno --password devops "$1" "$2" >/dev/null 2>&1; }
# shellcheck disable=SC2034
XENV='export DISPLAY=:0 XAUTHORITY=/home/aluno/.Xauthority DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus;'
SUDO="echo devops | sudo -S -p ''"
pid_vm() { pgrep -f 'VirtualBoxVM|VBoxHeadless' | head -n 1; }
cpu_proc() { awk '{print $14+$15}' "/proc/$1/stat" 2>/dev/null || echo 0; }

medir() { # $1 = nome do passo
  local n="$1" pid h1 h2 hz
  gcopy_to "$HERE/medir-ocioso.sh" /tmp/medir-ocioso.sh
  gcopy_to "$HERE/rastrear-timers.sh" /tmp/rastrear-timers.sh
  gsh "rm -f /tmp/medida-$n.txt* /tmp/timers-$n.txt*; setsid -f bash /tmp/medir-ocioso.sh 20 30 /tmp/medida-$n.txt >/dev/null 2>&1 < /dev/null; echo ok" >/dev/null
  pid="$(pid_vm)"; sleep 20; h1=$(cpu_proc "$pid"); sleep 30; h2=$(cpu_proc "$pid")
  for _ in $(seq 1 20); do gsh "test -e /tmp/medida-$n.txt.ok && echo pronto" | grep -q pronto && break; sleep 2; done
  # timers: 10 s, destacado, começando 15 s depois (sem o guestcontrol ativo)
  gsh "setsid -f bash -c \"sleep 15; echo devops | sudo -S -p '' bash /tmp/rastrear-timers.sh 10 /tmp/timers-$n.txt\" >/dev/null 2>&1 < /dev/null; echo ok" >/dev/null
  sleep 30
  for _ in $(seq 1 20); do gsh "test -e /tmp/timers-$n.txt.ok && echo pronto" | grep -q pronto && break; sleep 2; done
  gcopy_from "/tmp/medida-$n.txt" "$OUT/medida-$n.txt"
  gcopy_from "/tmp/timers-$n.txt" "$OUT/timers-$n.txt"
  hz=$(getconf CLK_TCK)
  log ""
  log "[$n] uptime $(gsh "cut -d. -f1 /proc/uptime")s | VirtualBox no computador: $(awk -v d=$((h2-h1)) -v hz="$hz" 'BEGIN{printf "%.0f%%", d*100/hz/30}') de 1 núcleo | dentro: $(head -n 2 "$OUT/medida-$n.txt" 2>/dev/null | tr '\n' ' ')"
  log "   irq/s: $(sed -n '/--- interr/,$p' "$OUT/medida-$n.txt" 2>/dev/null | sed -n '2,5p' | awk '{print $1"="$2}' | tr '\n' ' ')"
  log "   processos: $(sed -n '/--- processos/,/--- interr/p' "$OUT/medida-$n.txt" 2>/dev/null | sed -n '2,6p' | awk '{print $1, $3}' | tr '\n' ';')"
  sed 's/^/   /' "$OUT/timers-$n.txt" 2>/dev/null | head -n 40 | tee -a "$R"
}

VBoxManage import "$OVA" --vsys 0 --vmname "$VM" >/dev/null 2>&1 || { log "import falhou"; exit 1; }
VBoxManage setextradata global GUI/SuppressMessages "all" >/dev/null 2>&1 || true
VBoxManage showvminfo "$VM" --machinereadable | grep -E '^(graphicscontroller|hidpointing|usb|cpus|paravirtprovider)=' | tr '\n' ' ' | tee -a "$R"; echo | tee -a "$R"
VBoxManage startvm "$VM" --type gui >/dev/null 2>&1 || VBoxManage startvm "$VM" --type headless >/dev/null
for t in $(seq 5 5 600); do
  sleep 5; u="$(prop /VirtualBox/GuestInfo/OS/LoggedInUsers)"
  [ -n "$u" ] && [ "$u" != "0" ] && { log "login em ${t}s"; break; }
done
sleep 20
gsh "$SUDO apt-get update -qq >/dev/null 2>&1; $SUDO apt-get install -y -qq xdotool >/dev/null 2>&1; which xdotool" >/dev/null
gsh "cat /sys/devices/system/clocksource/clocksource0/current_clocksource; cat /sys/devices/system/cpu/cpuidle/current_driver /sys/devices/system/cpu/cpuidle/current_governor* 2>/dev/null; grep -o 'nohz[^ ]*' /proc/cmdline; dmesg 2>/dev/null | grep -iE 'clocksource|tsc|apic.*timer|hpet' | tail -n 8; $SUDO dmesg | grep -iE 'tsc|clocksource|timer' | tail -n 12" > "$OUT/relogio.txt" 2>&1
log "relógio da VM: $(head -n 3 "$OUT/relogio.txt" | tr '\n' ' ')"

# como no teste: o mouse passa pela janela e a tela é redimensionada
WID="$(xdotool search --name 'DevOps-Lab' 2>/dev/null | head -n 1)"
[ -n "$WID" ] && { xdotool windowactivate "$WID" 2>/dev/null; xdotool mousemove --window "$WID" 400 300; sleep 1; xdotool mousemove --window "$WID" 700 500; }
VBoxManage controlvm "$VM" setvideomodehint 1366 768 32; sleep 10
VBoxManage controlvm "$VM" setvideomodehint 1280 800 32; sleep 10
# o teste mexe no Docker antes de medir (docker images etc.)
gsh "docker images -q | wc -l" >/dev/null
gsh "$SUDO systemctl start devops-lab-apt-update.service; echo ok" >/dev/null

medir 0-boot1
gsh "systemctl --no-pager list-units --state=running --type=service | head -n 40; systemd-analyze blame | head -n 15" > "$OUT/servicos-boot1.txt" 2>&1
VBoxManage controlvm "$VM" acpipowerbutton; for _ in $(seq 1 60); do VBoxManage showvminfo "$VM" --machinereadable | grep -q '^VMState="poweroff"' && break; sleep 3; done
VBoxManage controlvm "$VM" poweroff >/dev/null 2>&1; sleep 3
VBoxManage guestproperty unset "$VM" /VirtualBox/GuestInfo/OS/LoggedInUsers >/dev/null 2>&1
VBoxManage startvm "$VM" --type gui >/dev/null 2>&1 || VBoxManage startvm "$VM" --type headless >/dev/null
for t in $(seq 5 5 600); do sleep 5; u="$(prop /VirtualBox/GuestInfo/OS/LoggedInUsers)"; [ -n "$u" ] && [ "$u" != "0" ] && { log "boot2: login em ${t}s"; break; }; done
sleep 150
gsh "systemctl --no-pager list-units --state=running --type=service | head -n 40" > "$OUT/servicos-boot2.txt" 2>&1
medir 1-boot2
sleep 240
medir 2-boot2-mais-tarde
VBoxManage controlvm "$VM" poweroff >/dev/null 2>&1; sleep 3
cp "$HOME/VirtualBox VMs/$VM/Logs/VBox.log" "$OUT/VBox.log" 2>/dev/null || true
VBoxManage unregistervm "$VM" --delete >/dev/null 2>&1 || true
