#!/usr/bin/env bash
# Tela preta com a VMSVGA: reproduz (vários boots com janela) e testa correções.
# Em cada boot: print pela janela do VirtualBox E print por dentro da VM (xwd) no mesmo
# momento, para saber se a imagem existe dentro da VM e só não chega à janela.
# Uso: ci/diag/tela-vmsvga.sh <arquivo.ova> <pasta> <correcao> <boots>
#   correcao: nenhuma | initramfs | xrandr-auto | sem-vboxclient-vmsvga
set -uo pipefail
OVA="$1"; OUT="$2"; FIX="$3"; BOOTS="${4:-4}"; VM="DevOps-Lab"
mkdir -p "$OUT"; R="$OUT/RESUMO-$FIX.txt"
log()  { echo "$*" | tee -a "$R"; }
prop() { VBoxManage guestproperty get "$VM" "$1" 2>/dev/null | sed -n 's/^Value: //p'; }
gsh()  { timeout 300 VBoxManage guestcontrol "$VM" run --username aluno --password devops \
  --wait-stdout --wait-stderr --timeout 280000 -- /bin/bash -lc "$1" 2>&1; }
XENV='export DISPLAY=:0 XAUTHORITY=/home/aluno/.Xauthority;'
SUDO="echo devops | sudo -S -p ''"
cores() { convert "$1" -format '%k' info: 2>/dev/null || echo 0; }
desliga() {
  VBoxManage controlvm "$VM" acpipowerbutton >/dev/null 2>&1
  for _ in $(seq 1 60); do VBoxManage showvminfo "$VM" --machinereadable | grep -q '^VMState="poweroff"' && break; sleep 2; done
  VBoxManage controlvm "$VM" poweroff >/dev/null 2>&1; sleep 3
}
espera_login() {
  VBoxManage guestproperty unset "$VM" /VirtualBox/GuestInfo/OS/LoggedInUsers >/dev/null 2>&1
  for _ in $(seq 1 90); do u="$(prop /VirtualBox/GuestInfo/OS/LoggedInUsers)"; [ -n "$u" ] && [ "$u" != 0 ] && return 0; sleep 2; done
  return 1
}

VBoxManage import "$OVA" --vsys 0 --vmname "$VM" >/dev/null 2>&1 || { log "import falhou"; exit 1; }
VBoxManage setextradata global GUI/SuppressMessages "all" >/dev/null 2>&1 || true
# prepara a correção num boot com a placa atual
VBoxManage startvm "$VM" --type headless >/dev/null; espera_login; sleep 15
gsh "$SUDO apt-get update -qq >/dev/null 2>&1; $SUDO apt-get install -y -qq x11-apps x11-utils imagemagick-6.q16 >/dev/null 2>&1; which xwd" >/dev/null
case "$FIX" in
  initramfs)
    gsh "printf 'vmwgfx\nvboxvideo\n' | $SUDO tee -a /etc/initramfs-tools/modules >/dev/null; $SUDO update-initramfs -u >/dev/null 2>&1; $SUDO lsinitramfs /boot/initrd.img | grep -E 'vmwgfx|vboxvideo'" | tee -a "$R" ;;
  xrandr-auto)
    gsh "mkdir -p ~/.config/autostart; printf '[Desktop Entry]\nType=Application\nName=xrandr auto\nExec=sh -c \"sleep 2; xrandr --auto\"\nNoDisplay=true\n' > ~/.config/autostart/xrandr-auto.desktop; cat ~/.config/autostart/xrandr-auto.desktop" | tee -a "$R" ;;
  sem-vboxclient-vmsvga)
    gsh "$SUDO sed -i 's|^\(.*--vmsvga-session.*\)$|# \\1|' /etc/X11/Xsession.d/98vboxadd-xclient; grep -n vmsvga /etc/X11/Xsession.d/98vboxadd-xclient" | tee -a "$R" ;;
esac
desliga
VBoxManage modifyvm "$VM" --graphicscontroller vmsvga

pretas=0
for b in $(seq 1 "$BOOTS"); do
  P="$OUT/$FIX-boot$b"; mkdir -p "$P"
  VBoxManage startvm "$VM" --type gui >/dev/null 2>&1
  espera_login; sleep 25
  VBoxManage controlvm "$VM" screenshotpng "$P/janela.png" >/dev/null 2>&1
  gsh "$XENV xwd -root -silent > /tmp/d.xwd" >/dev/null
  VBoxManage guestcontrol "$VM" copyfrom --username aluno --password devops /tmp/d.xwd "$P/dentro.xwd" >/dev/null 2>&1
  convert "xwd:$P/dentro.xwd" "$P/dentro.png" 2>/dev/null; rm -f "$P/dentro.xwd"
  cj=$(cores "$P/janela.png"); cd=$(cores "$P/dentro.png")
  [ "${cj:-0}" -le 4 ] && pretas=$((pretas+1))
  info="$(gsh "$XENV xrandr | head -n 3 | tr '\n' ' '; echo; $SUDO dmesg | grep -m2 -E 'vmwgfx.*(Initialized|fb0)' | tr '\n' ' '; echo; pgrep -a VBoxClient | tr '\n' ' '")"
  log "boot $b: janela do VirtualBox=$cj cores | dentro da VM=$cd cores | $(echo "$info" | tr '\n' '|' | cut -c1-400)"
  if [ "${cj:-0}" -le 4 ]; then
    gsh "$XENV xrandr --auto; echo ok" >/dev/null; sleep 5
    VBoxManage controlvm "$VM" screenshotpng "$P/janela-depois-xrandr-auto.png" >/dev/null 2>&1
    log "        preta: depois de 'xrandr --auto' a janela ficou com $(cores "$P/janela-depois-xrandr-auto.png") cores"
    gsh "grep -E 'modeset|EE|vmware|Output|Virtual' /var/log/Xorg.0.log | head -n 40; tail -n 20 ~/.xsession-errors 2>/dev/null" > "$P/xorg.txt" 2>&1
  fi
  [ $((b % 2)) -eq 1 ] && desliga || { VBoxManage controlvm "$VM" poweroff >/dev/null 2>&1; sleep 3; }
  cp "$HOME/VirtualBox VMs/$VM/Logs/VBox.log" "$P/VBox.log" 2>/dev/null || true
done
log "RESULTADO $FIX: janela preta em $pretas de $BOOTS boots"
VBoxManage unregistervm "$VM" --delete >/dev/null 2>&1 || true
