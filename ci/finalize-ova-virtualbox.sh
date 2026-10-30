#!/usr/bin/env bash
# Gera o .ova final com o próprio VirtualBox, a partir do .ova "compatível"
# convertido do QEMU, aplicando as configurações recomendadas para Linux:
#   vídeo VBoxSVGA 128 MB (com VMSVGA a tela ficava preta, inclusive com Hyper-V), 1 porta SATA, mouse USB tablet, área de transferência
#   e arrastar/soltar bidirecionais, áudio desligado.
# Uso: ci/finalize-ova-virtualbox.sh <entrada.ova> <pasta-saida>
set -euxo pipefail
IN="$1"
OUTDIR="$2"
VM="DevOps-Lab"
DESC="Ubuntu 24.04 LTS + XFCE com VS Code, Docker, Docker Compose, Git, Ansible, Terraform, Python e Jenkins. Usuario: aluno / Senha: devops"
mkdir -p "$OUTDIR"

VBoxManage import "$IN" --vsys 0 --vmname "$VM"
CTL="$(VBoxManage showvminfo "$VM" --machinereadable | sed -n 's/^storagecontrollername0="\(.*\)"$/\1/p')"
VBoxManage storagectl "$VM" --name "$CTL" --portcount 1 --hostiocache on
DISCO="$(VBoxManage showvminfo "$VM" --machinereadable | sed -n "s/^\"$CTL-ImageUUID-0-0\"=\"\(.*\)\"$/\1/p")"
[ -n "$DISCO" ] && VBoxManage storageattach "$VM" --storagectl "$CTL" --port 0 --device 0 --type hdd \
  --medium "$DISCO" --nonrotational on --discard on || echo "AVISO: não marquei o disco como SSD"
VBoxManage modifyvm "$VM" \
  --ostype Ubuntu_64 --cpus 2 --memory 4096 --ioapic on --rtc-use-utc on \
  --graphicscontroller vboxsvga --vram 128 \
  --usb-ohci on --mouse usbtablet \
  --clipboard-mode bidirectional --drag-and-drop bidirectional \
  --audio-enabled off --nictype1 virtio \
  --description "$DESC"
VBoxManage showvminfo "$VM" --machinereadable \
  | grep -E '^(nic|SATA|AHCI|.*Rotational|.*Discard|hostiocache|graphicscontroller|vram|mouse|clipboard|draganddrop|storagecontrollerportcount0|usb|audio)' || true

VBoxManage export "$VM" -o "$OUTDIR/DevOps-Lab.ova" --options manifest,nomacs \
  --vsys 0 --product "DevOps Lab" --version "1.0" --description "$DESC"
VBoxManage unregistervm "$VM" --delete

cd "$OUTDIR"
sha256sum DevOps-Lab.ova > DevOps-Lab.ova.sha256
ls -l
SIZE=$(stat -c %s DevOps-Lab.ova)
echo "::notice title=ova-final::DevOps-Lab.ova = $SIZE bytes"
# Limite do GitHub para arquivos de Release: 2 GiB
[ "$SIZE" -lt 2147483648 ] || { echo "::error::.ova final passou de 2 GiB"; exit 1; }
