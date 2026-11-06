#!/usr/bin/env bash
# Mede o quanto a VM pesa parada (dentro da VM e no computador) e o tempo para abrir
# programas, ligando/desligando uma coisa de cada vez. Também testa a correção da tela
# preta da VMSVGA (driver vmwgfx carregado cedo, no initramfs).
# Uso: ci/diag/fluidez.sh <arquivo.ova> <pasta> <variante>
#   variante: atual | ps2 | vmsvga-cedo
set -uo pipefail
OVA="$1"; OUT="$2"; VAR="$3"; VM="DevOps-Lab"; HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$OUT"; R="$OUT/RESUMO-$VAR.txt"
log()  { echo "$*" | tee -a "$R"; }
prop() { VBoxManage guestproperty get "$VM" "$1" 2>/dev/null | sed -n 's/^Value: //p'; }
gsh()  { timeout 300 VBoxManage guestcontrol "$VM" run --username aluno --password devops \
  --wait-stdout --wait-stderr --timeout 280000 -- /bin/bash -lc "$1" 2>&1; }
gcopy_to()   { VBoxManage guestcontrol "$VM" copyto --username aluno --password devops "$1" "$2" >/dev/null 2>&1; }
gcopy_from() { VBoxManage guestcontrol "$VM" copyfrom --username aluno --password devops "$1" "$2" >/dev/null 2>&1; }
XENV='export DISPLAY=:0 XAUTHORITY=/home/aluno/.Xauthority DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus;'
SUDO="echo devops | sudo -S -p ''"

liga_e_espera() { # boot com janela; mede quanto tempo a janela fica preta
  local P="$OUT/$VAR-$1"; mkdir -p "$P"
  VBoxManage guestproperty unset "$VM" /VirtualBox/GuestInfo/OS/LoggedInUsers >/dev/null 2>&1
  VBoxManage startvm "$VM" --type gui >/dev/null 2>&1 || VBoxManage startvm "$VM" --type headless >/dev/null
  local preta=0 login="" c
  for t in $(seq 2 2 120); do
    sleep 2
    if VBoxManage controlvm "$VM" screenshotpng "$P/t.png" >/dev/null 2>&1; then c=$(convert "$P/t.png" -format '%k' info: 2>/dev/null || echo 0); else c=0; fi
    [ "${c:-0}" -le 4 ] && preta=$((preta+2))
    u="$(prop /VirtualBox/GuestInfo/OS/LoggedInUsers)"
    [ -z "$login" ] && [ -n "$u" ] && [ "$u" != "0" ] && login=$t
    [ -n "$login" ] && [ "$t" -ge $((login+20)) ] && [ "${c:-0}" -gt 100 ] && break
  done
  cp "$P/t.png" "$P/depois-do-login.png" 2>/dev/null; rm -f "$P/t.png"
  log "[$1] login em ${login:-NUNCA}s | janela preta por ${preta}s | tela no fim: ${c:-0} cores"
}

pid_vm() { pgrep -f 'VirtualBoxVM|VBoxHeadless' | head -n 1; }
cpu_proc() { awk '{print $14+$15}' "/proc/$1/stat" 2>/dev/null || echo 0; }

medir() { # $1 = nome do passo
  gcopy_to "$HERE/../vm-tests/medir-ocioso.sh" /tmp/medir-ocioso.sh
  gsh "setsid -f bash /tmp/medir-ocioso.sh 20 30 /tmp/medida-$1.txt >/dev/null 2>&1 < /dev/null; echo ok" >/dev/null
  local pid h1 h2; pid="$(pid_vm)"; sleep 20; h1=$(cpu_proc "$pid"); sleep 30; h2=$(cpu_proc "$pid")
  for _ in $(seq 1 20); do gsh "test -e /tmp/medida-$1.txt.ok && echo pronto" | grep -q pronto && break; sleep 2; done
  gcopy_from "/tmp/medida-$1.txt" "$OUT/medida-$VAR-$1.txt"
  local hz; hz=$(getconf CLK_TCK)
  log "[$1] VirtualBox no computador: $(awk -v d=$((h2-h1)) -v hz="$hz" 'BEGIN{printf "%.0f%%", d*100/hz/30}') de 1 núcleo | dentro da VM: $(head -n 2 "$OUT/medida-$VAR-$1.txt" 2>/dev/null | tr '\n' ' ')"
  log "        $(sed -n '/--- processos/,/--- interr/p' "$OUT/medida-$VAR-$1.txt" 2>/dev/null | sed -n '2,5p' | tr -s ' ' | tr '\n' ';')"
  log "        irq/s: $(sed -n '/--- interr/,$p' "$OUT/medida-$VAR-$1.txt" 2>/dev/null | sed -n '2,5p' | awk '{print $1"="$2}' | tr '\n' ' ')"
}

abrir() { # tempo para abrir um programa até a janela aparecer
  gsh "$XENV t0=\$(date +%s%N); setsid -f $1 >/dev/null 2>&1; xdotool search --sync --onlyvisible --class '$2' >/dev/null; t1=\$(date +%s%N); echo \$(( (t1-t0)/1000000 )) ms; sleep 1; pkill -f '$1' || true"
}

VBoxManage import "$OVA" --vsys 0 --vmname "$VM" >/dev/null 2>&1 || { log "import falhou"; exit 1; }
case "$VAR" in
  ps2) VBoxManage modifyvm "$VM" --mouse ps2 --usb-ohci off ;;
esac
VBoxManage setextradata global GUI/SuppressMessages "all" >/dev/null 2>&1 || true
VBoxManage showvminfo "$VM" --machinereadable | grep -E '^(graphicscontroller|hidpointing|usb|cpus)=' | tr '\n' ' ' | tee -a "$R"; echo | tee -a "$R"

liga_e_espera boot1
gsh "$SUDO apt-get update -qq >/dev/null 2>&1; $SUDO apt-get install -y -qq xdotool >/dev/null 2>&1; which xdotool" >/dev/null

if [ "$VAR" = vmsvga-cedo ]; then
  gsh "echo vmwgfx | $SUDO tee -a /etc/initramfs-tools/modules >/dev/null; $SUDO update-initramfs -u >/dev/null 2>&1; lsinitramfs /boot/initrd.img | grep -c vmwgfx" | tee -a "$R"
  VBoxManage controlvm "$VM" acpipowerbutton; for _ in $(seq 1 60); do VBoxManage showvminfo "$VM" --machinereadable | grep -q '^VMState="poweroff"' && break; sleep 2; done
  VBoxManage controlvm "$VM" poweroff >/dev/null 2>&1; sleep 3
  VBoxManage modifyvm "$VM" --graphicscontroller vmsvga
  liga_e_espera boot2-vmsvga
  gsh "pgrep -a VBoxDRMClient; $SUDO dmesg | grep -iE 'vmwgfx.*(Initialized|fb0)'; $SUDO journalctl -b -u virtualbox-guest-utils --no-pager | tail -n 5" > "$OUT/vmsvga-cedo-detalhes.txt" 2>&1
  log "VBoxDRMClient rodando: $(grep -c VBoxDRMClient "$OUT/vmsvga-cedo-detalhes.txt")"
  for res in "1366 768" "1280 800" "1024 768"; do
    # shellcheck disable=SC2086
    VBoxManage controlvm "$VM" setvideomodehint $res 32; sleep 10
    VBoxManage controlvm "$VM" screenshotpng "$OUT/vmsvga-cedo-${res// /x}.png" >/dev/null 2>&1
    log "pedido ${res// /x}: tela $(convert "$OUT/vmsvga-cedo-${res// /x}.png" -format '%k cores %wx%h' info: 2>/dev/null) | xrandr: $(gsh "$XENV xrandr | grep -m1 -oE 'current [0-9]+ x [0-9]+'")"
  done
fi

sleep 60   # Jenkins liga 45 s depois do boot; espera ele assentar
log "abrir terminal: $(abrir xfce4-terminal Xfce4-terminal | tail -n 1) | abrir Thunar: $(abrir thunar Thunar | tail -n 1)"
medir 0-como-vem
gsh "pkill -f 'VBoxClient --draganddrop'; echo ok" >/dev/null
medir 1-sem-arrastar-soltar
gsh "$XENV xfconf-query -c xfwm4 -p /general/vblank_mode -s off; echo ok" >/dev/null
medir 2-vblank-off
gsh "$XENV xfconf-query -c xfwm4 -p /general/use_compositing -s false; echo ok" >/dev/null
medir 3-sem-compositor
gsh "$SUDO systemctl stop jenkins; echo ok" >/dev/null
medir 4-sem-jenkins
gsh "pkill -f 'VBoxClient --clipboard'; pkill -f 'VBoxClient --seamless'; echo ok" >/dev/null
medir 5-sem-clipboard-seamless
log "abrir terminal (no fim): $(abrir xfce4-terminal Xfce4-terminal | tail -n 1) | abrir Thunar: $(abrir thunar Thunar | tail -n 1)"
VBoxManage controlvm "$VM" poweroff >/dev/null 2>&1; sleep 3
cp "$HOME/VirtualBox VMs/$VM/Logs/VBox.log" "$OUT/VBox-$VAR.log" 2>/dev/null || true
VBoxManage unregistervm "$VM" --delete >/dev/null 2>&1 || true
