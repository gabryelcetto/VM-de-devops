#!/usr/bin/env bash
# Varredura de QA da VM no VirtualBox COM JANELA (como o aluno usa), num X virtual (Xvfb):
#   - tela preta: print da janela do VirtualBox a cada 2 s durante o boot, vários boots
#   - mouse: move o mouse do "computador" (Xvfb) sobre a janela e confere se o ponteiro
#     DENTRO da VM vai para o mesmo lugar (integração do mouse = sem precisar capturar)
#   - redimensionar: pede outra resolução (como maximizar a janela) e confere a tela
#   - logs: VBox.log, Xorg, LightDM, dmesg, journal, serviços com falha
# Uso: ci/diag-vm.sh <arquivo.ova> <pasta-de-resultados> <video> <boots>
#   video: vboxsvga | vmsvga
set -uo pipefail
OVA="$1"; OUT="$2"; VID="$3"; BOOTS="${4:-3}"; VM="DevOps-Lab"
mkdir -p "$OUT"
R="$OUT/RESUMO-$VID.txt"
log()  { echo "$*" | tee -a "$R"; }
prop() { VBoxManage guestproperty get "$VM" "$1" 2>/dev/null | sed -n 's/^Value: //p'; }
gsh()  { timeout 300 VBoxManage guestcontrol "$VM" run --username aluno --password devops \
  --wait-stdout --wait-stderr --timeout 280000 -- /bin/bash -lc "$1" 2>&1; }
XENV='export DISPLAY=:0 XAUTHORITY=/home/aluno/.Xauthority;'
brilho() { # $1 = png -> "cores brilho(0-100)"
  convert "$1" -format '%k %[fx:round(mean*100)]' info: 2>/dev/null || echo "0 0"
}
shot() { # $1 = arquivo; print da tela da VM (pelo VirtualBox)
  VBoxManage controlvm "$VM" screenshotpng "$1" >/dev/null 2>&1 && [ -s "$1" ]
}
janela_host() { # geometria da janela da VM no X do "computador": X Y LARGURA ALTURA
  local w; w="$(xdotool search --name "^$VM" 2>/dev/null | tail -n 1)"
  [ -n "$w" ] || return 1
  xdotool getwindowgeometry --shell "$w" | awk -F= '/^X=/{x=$2}/^Y=/{y=$2}/^WIDTH=/{l=$2}/^HEIGHT=/{a=$2}END{print x, y, l, a}'
}

VBoxManage import "$OVA" --vsys 0 --vmname "$VM" >/dev/null 2>&1 || { log "import falhou"; exit 1; }
VBoxManage modifyvm "$VM" --graphicscontroller "$VID"
VBoxManage showvminfo "$VM" --machinereadable | grep -E '^(graphicscontroller|vram|hidpointing|hidkeyboard|usb|usbohci|cpus|memory)=' | tee -a "$R"
# Desliga as dicas da interface do VirtualBox que cobrem a janela
VBoxManage setextradata global GUI/SuppressMessages "all" >/dev/null 2>&1 || true
VBoxManage setextradata global GUI/NotificationCenter/Alignment "Bottom" >/dev/null 2>&1 || true

for b in $(seq 1 "$BOOTS"); do
  log ""
  log "======== $VID boot $b ========"
  P="$OUT/$VID-boot$b"; mkdir -p "$P"
  VBoxManage startvm "$VM" --type gui >/dev/null 2>&1 || { log "startvm gui falhou"; VBoxManage startvm "$VM" --type headless >/dev/null; }
  # Linha do tempo da tela (o que aparece na janela do aluno)
  preta_seg=0; login_t=""; ultima_preta=""
  for t in $(seq 2 2 150); do
    sleep 2
    f="$P/t$(printf %03d "$t").png"
    if shot "$f"; then read -r c m < <(brilho "$f"); else c=0; m=0; fi
    u="$(prop /VirtualBox/GuestInfo/OS/LoggedInUsers)"
    [ -z "$login_t" ] && [ -n "$u" ] && [ "$u" != "0" ] && login_t=$t
    if [ "${c:-0}" -le 4 ]; then preta_seg=$((preta_seg+2)); ultima_preta=$t; fi
    echo "t=${t}s cores=$c brilho=$m usuarios=${u:-}" >> "$P/linha-do-tempo.txt"
    # depois do login, espera 20 s de tela boa e segue
    if [ -n "$login_t" ] && [ "$t" -ge $((login_t+20)) ] && [ "${c:-0}" -gt 100 ]; then break; fi
  done
  log "login automático em: ${login_t:-NUNCA}s | segundos com a janela preta: $preta_seg | última vez preta: t=${ultima_preta:--}s"
  # mantém só alguns prints (o primeiro preto, o último preto, o final)
  ls "$P"/t*.png 2>/dev/null | awk 'NR%5!=1' | head -n -1 | xargs -r rm -f
  sleep 5
  F="$P/final.png"; shot "$F"; log "tela 25 s depois do login: $(brilho "$F") (cores brilho)"

  # ---------------- mouse
  gsh "echo devops | sudo -S -p '' apt-get install -y -qq xdotool xinput x11-utils >/dev/null 2>&1; which xdotool xinput" >/dev/null
  G="$(janela_host)"; log "janela da VM no computador (x y larg alt): ${G:-não achei}"
  if [ -n "$G" ]; then
    read -r WX WY WL WA <<<"$G"
    for pos in "0.25 0.35" "0.70 0.60" "0.50 0.20"; do
      read -r fx fy <<<"$pos"
      hx=$(awk -v a="$WX" -v l="$WL" -v f="$fx" 'BEGIN{print int(a+l*f)}')
      hy=$(awk -v a="$WY" -v l="$WA" -v f="$fy" 'BEGIN{print int(a+l*f)}')
      xdotool mousemove "$hx" "$hy"; sleep 0.4; xdotool mousemove_relative 1 1; sleep 1.5
      g="$(gsh "$XENV xdotool getmouselocation" | tr '\n' ' ')"
      log "mouse do computador em ($hx,$hy) [${fx}x ${fy}y da janela] -> ponteiro dentro da VM: $g"
    done
  fi
  {
    echo "===== VBox.log: mouse / USB tablet / Guest Additions"
    grep -iE "mouse|tablet|absolute|UHGsmi|VMMDev: Guest Additions|Additions (information|capability)|GUI:.*(Mouse|mouse)" "$HOME/VirtualBox VMs/$VM/Logs/VBox.log" | tail -n 60
    echo "===== /proc/bus/input/devices"; gsh "cat /proc/bus/input/devices"
    echo "===== xinput list"; gsh "$XENV xinput list"
    echo "===== Xorg: dispositivos de entrada"; gsh "grep -iE 'input|mouse|tablet|vbox|Adding' /var/log/Xorg.0.log | head -n 60"
  } > "$P/mouse.txt" 2>&1

  # ---------------- redimensionar (maximizar a janela)
  VBoxManage controlvm "$VM" setvideomodehint 1366 768 32 >/dev/null 2>&1; sleep 12
  shot "$P/redimensionada.png"; log "depois de pedir 1366x768: $(brilho "$P/redimensionada.png") | xrandr: $(gsh "$XENV xrandr 2>&1 | grep -m1 -oE 'current [0-9]+ x [0-9]+'")"
  VBoxManage controlvm "$VM" setvideomodehint 1280 800 32 >/dev/null 2>&1; sleep 12
  shot "$P/redimensionada2.png"; log "depois de pedir 1280x800: $(brilho "$P/redimensionada2.png") | xrandr: $(gsh "$XENV xrandr 2>&1 | grep -m1 -oE 'current [0-9]+ x [0-9]+'")"

  # ---------------- logs do sistema
  {
    echo "===== boot (systemd-analyze)"; gsh "systemd-analyze; systemd-analyze blame | head -n 15; systemd-analyze critical-chain graphical.target"
    echo "===== serviços com falha"; gsh "systemctl --failed --no-legend"
    echo "===== erros do boot (journal -p err)"; gsh "echo devops | sudo -S -p '' journalctl -b -p err --no-pager | tail -n 80"
    echo "===== avisos do kernel"; gsh "echo devops | sudo -S -p '' dmesg --level=err,warn | tail -n 60"
    echo "===== vídeo no kernel"; gsh "echo devops | sudo -S -p '' dmesg | grep -iE 'drm|vmwgfx|vboxvideo|fb0|vboxguest|vboxsf|input' | head -n 60; lsmod | grep -E 'vbox|vmwgfx|drm'; ls -l /dev/dri"
    echo "===== Xorg (EE/WW)"; gsh "grep -E '\((EE|WW)\)' /var/log/Xorg.0.log; grep -E 'Loading.*drv|modeset|Output .* connected|Using' /var/log/Xorg.0.log | head -n 30"
    echo "===== Xorg anterior (Xorg.0.log.old)"; gsh "grep -E '\((EE|WW)\)|Fatal|no screens' /var/log/Xorg.0.log.old 2>/dev/null | head -n 30"
    echo "===== LightDM"; gsh "echo devops | sudo -S -p '' tail -n 60 /var/log/lightdm/lightdm.log; echo devops | sudo -S -p '' cat /var/log/lightdm/x-0.log 2>/dev/null | grep -E 'EE|Fatal' | head"
    echo "===== sessão (xsession-errors)"; gsh "tail -n 60 ~/.xsession-errors 2>/dev/null"
    echo "===== VBoxClient"; gsh "pgrep -a VBoxClient; pgrep -a VBoxDRMClient; systemctl status vboxadd-service virtualbox-guest-utils --no-pager 2>&1 | head -n 20"
    echo "===== tela: proteção de tela / DPMS"; gsh "$XENV xset q | sed -n '/Screen Saver/,/DPMS/p;/DPMS is/p'"
    echo "===== memória"; gsh "free -m; uptime"
    echo "===== fluidez: CPU com a VM parada (top, 2 amostras de 5 s)"; gsh "top -b -n 2 -d 5 -o %CPU -w 200 | awk '/^top -/{n++} n==2' | head -n 25"
    echo "===== fluidez: vmstat (r = fila de CPU, wa = espera de disco, st = roubado pelo computador)"; gsh "vmstat 2 6"
    echo "===== fluidez: compositor do XFCE"; gsh "$XENV for k in use_compositing vblank_mode sync_to_vblank show_frame_shadow show_popup_shadow show_dock_shadow frame_opacity move_opacity resize_opacity unredirect_overlays zoom_desktop; do printf '%s=' \$k; xfconf-query -c xfwm4 -p /general/\$k 2>&1; done"
    echo "===== fluidez: processos que acordam muito (lista de serviços ligados)"; gsh "systemctl list-units --type=service --state=running --no-legend | awk '{print \$1}'; systemctl --user list-units --type=service --state=running --no-legend 2>/dev/null | awk '{print \$1}'"
    echo "===== fluidez: tempo para desenhar (x11perf-like: xdotool + xwd 5 vezes)"; gsh "$XENV for i in 1 2 3 4 5; do /usr/bin/time -f %e xwd -root -silent >/dev/null; done 2>&1"
    echo "===== VBox.log: modo de execução (VT-x/AMD-V ou Hyper-V/NEM = tartaruga)"; grep -iE "HM: HMR3Init|NEM|Hyper-V|VT-x|AMD-V|nested paging|Paravirt|TSC mode" "$HOME/VirtualBox VMs/$VM/Logs/VBox.log" | head -n 20
  } > "$P/sistema.txt" 2>&1

  # ---------------- desligar (alternando: pelo botão (ACPI) e "puxando a tomada")
  if [ $((b % 2)) -eq 1 ]; then
    VBoxManage controlvm "$VM" acpipowerbutton >/dev/null 2>&1
    for _ in $(seq 1 60); do VBoxManage showvminfo "$VM" --machinereadable | grep -q '^VMState="poweroff"' && break; sleep 2; done
    log "desligou pelo botão (ACPI)"
  fi
  VBoxManage controlvm "$VM" poweroff >/dev/null 2>&1 || true
  for _ in $(seq 1 30); do VBoxManage showvminfo "$VM" --machinereadable | grep -q '^VMState="poweroff"' && break; sleep 1; done
  sleep 3
  cp "$HOME/VirtualBox VMs/$VM/Logs/VBox.log" "$P/VBox.log" 2>/dev/null || true
done
VBoxManage unregistervm "$VM" --delete >/dev/null 2>&1 || true
