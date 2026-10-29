#!/usr/bin/env bash
# ==========================================================================
#  DevOps-Lab-UVV - gera output/DevOps-Lab-UVV.ova (Linux / macOS Intel)
#  Uso:  ./build.sh                 (padrão: 2 CPUs, 4096 MB)
#        CPUS=4 MEMORY=6144 HEADLESS=true ./build.sh
# ==========================================================================
set -euo pipefail
cd "$(dirname "$0")"

CPUS="${CPUS:-2}"
MEMORY="${MEMORY:-4096}"
HEADLESS="${HEADLESS:-false}"

echo "== DevOps-Lab-UVV: preparando build =="

if ! command -v VBoxManage >/dev/null 2>&1; then
  echo "VirtualBox não encontrado. Instale em https://www.virtualbox.org/wiki/Downloads" >&2
  exit 1
fi
echo "VirtualBox: $(VBoxManage --version)"

if ! command -v packer >/dev/null 2>&1; then
  echo "Packer não encontrado. Instale: https://developer.hashicorp.com/packer/install" >&2
  exit 1
fi
echo "Packer: $(packer version | head -n 1)"

ISO_NAME="ubuntu-24.04.5-live-server-amd64.iso"
if latest="$(curl -fsSL https://releases.ubuntu.com/24.04/SHA256SUMS \
              | grep -oE 'ubuntu-24\.04(\.[0-9]+)*-live-server-amd64\.iso' | head -n 1)" \
   && [ -n "$latest" ]; then
  ISO_NAME="$latest"
else
  echo "Não foi possível consultar a ISO mais recente; usando ${ISO_NAME}"
fi
echo "ISO: ${ISO_NAME}"
echo
echo "O build leva de 30 a 60 minutos."
echo

packer init .
packer build -force \
  -var "iso_name=${ISO_NAME}" \
  -var "cpus=${CPUS}" \
  -var "memory=${MEMORY}" \
  -var "headless=${HEADLESS}" \
  devops-lab.pkr.hcl

echo
echo "Pronto! Arquivo gerado: $(pwd)/output/DevOps-Lab-UVV.ova"
echo "Importe no VirtualBox em: Arquivo > Importar Appliance"
