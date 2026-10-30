#!/usr/bin/env bash
# Diagnóstico da tela preta: liga o .ova com uma configuração de vídeo e tira prints
# pelo PRÓPRIO VirtualBox (o que aparece na janela do aluno), não por dentro da VM.
# Uso: ci/diag-video.sh <arquivo.ova> <pasta> <variante>
#   variantes: atual | vram16 | vboxsvga | vboxvga | modesetting | modesetting-vram16
set -uo pipefail
OVA="$1"; OUT="$2"; VAR="$3"; VM="DevOps-Lab"
mkdir -p "$OUT"
R="$OUT/resumo-$VAR.txt"
log() { echo "$*" | tee -a "$R"; }
prop() { VBoxManage guestproperty get "$VM" "$1" 2>/dev/null | sed -n 's/^Value: //p'; }
gsh() { timeout 300 VBoxManage guestcontrol "$VM" run --username aluno --password devops \
  --wait-stdout --wait-stderr --timeout 280000 -- /bin/bash -lc "$1" 2>&1; }
shot() { # $1 = nome; devolve nº de cores do print do VirtualBox
  VBoxManage controlvm "$VM" screenshotpng "$OUT/$VAR-$1.png" >/dev/null 2>&1 || { echo 0; return; }
  convert "$OUT/$VAR-$1.png" -format '%k %wx%h' info: 2>/dev/null || echo 0
}

VBoxManage import "$OVA" --vsys 0 --vmname "$VM" >/dev/null 2>&1 || { log "import falhou"; exit 1; }
case "$VAR" in
  vram16|modesetting-vram16) VBoxManage modifyvm "$VM" --vram 16 ;;
  vboxsvga) VBoxManage modifyvm "$VM" --graphicscontroller vboxsvga ;;
  vboxvga)  VBoxManage modifyvm "$VM" --graphicscontroller vboxvga --vram 32 ;;
  vboxsvga16) VBoxManage modifyvm "$VM" --graphicscontroller vboxsvga --vram 16 ;;
  vboxsvga-lento) VBoxManage modifyvm "$VM" --graphicscontroller vboxsvga --cpu-execution-cap 35 ;;
esac
VBoxManage showvminfo "$VM" --machinereadable | grep -E '^(graphicscontroller|vram|cpus|memory)=' | tee -a "$R"
VBoxManage startvm "$VM" --type headless >/dev/null

t=0
for s in 10 20 30 45 60 90; do
  sleep $((s - t)); t=$s
  log "t=${s}s  print do VirtualBox: $(shot "t$s")  usuarios=$(prop /VirtualBox/GuestInfo/OS/LoggedInUsers)"
done
for _ in $(seq 1 60); do [ -n "$(prop /VirtualBox/GuestInfo/Net/0/V4/IP)" ] && break; sleep 5; done
sleep 10

if [ "${VAR#modesetting}" != "$VAR" ]; then
  gsh "printf 'Section \"Device\"\n  Identifier \"gpu\"\n  Driver \"modesetting\"\nEndSection\n' > /tmp/v.conf; echo devops | sudo -S -p '' install -D -m 0644 /tmp/v.conf /etc/X11/xorg.conf.d/10-devops-lab-video.conf; cat /etc/X11/xorg.conf.d/10-devops-lab-video.conf; echo devops | sudo -S -p '' systemctl restart lightdm" >> "$R"
  sleep 40
  log "depois de trocar para modesetting: $(shot depois-modesetting)"
fi

log "final (print do VirtualBox): $(shot final)"
VBoxManage controlvm "$VM" setvideomodehint 1366 768 32 >/dev/null 2>&1
sleep 15
log "depois de pedir 1366x768 (como ao redimensionar a janela): $(shot redimensionada)"
{
  echo "===== módulos de vídeo"; gsh "lsmod | grep -E 'vmwgfx|vboxvideo|drm' ; ls /dev/dri"
  echo "===== Xorg: driver e erros"; gsh "grep -E '\((II|EE|WW)\).*(LoadModule|driver|Driver|glamor|vmware|modeset|VMWARE|Output|EE)' /var/log/Xorg.0.log | head -n 60"
  echo "===== xrandr"; gsh "DISPLAY=:0 XAUTHORITY=/home/aluno/.Xauthority xrandr 2>&1 | head"
  echo "===== dmesg drm"; gsh "echo devops | sudo -S -p '' dmesg | grep -iE 'drm|vmwgfx|vboxvideo|fb' | head -n 40"
  echo "===== VBoxClient"; gsh "pgrep -a VBoxClient; pgrep -a VBoxDRMClient"
} > "$OUT/guest-$VAR.txt" 2>&1
VBoxManage controlvm "$VM" poweroff >/dev/null 2>&1 || true
sleep 3
cp "$HOME/VirtualBox VMs/$VM/Logs/VBox.log" "$OUT/VBox-$VAR.log" 2>/dev/null || true
