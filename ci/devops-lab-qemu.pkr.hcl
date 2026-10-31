#############################################################################
#  DevOps-Lab - build na nuvem (GitHub Actions) com QEMU/KVM
#  Gera um disco qcow2 que depois vira DevOps-Lab.ova (ci/make-ova.py)
#  Usa os mesmos http/ scripts/ files/ do build local com VirtualBox.
#############################################################################

packer {
  required_version = ">= 1.10.0"
  required_plugins {
    qemu = {
      version = ">= 1.1.0"
      source  = "github.com/hashicorp/qemu"
    }
  }
}

variable "iso_base_url" {
  type    = string
  default = "https://releases.ubuntu.com/24.04"
}

variable "iso_name" {
  type    = string
  default = "ubuntu-24.04.5-live-server-amd64.iso"
}

variable "username" {
  type    = string
  default = "aluno"
}

variable "password" {
  type      = string
  default   = "devops"
  sensitive = true
}

source "qemu" "devops_lab" {
  vm_name      = "DevOps-Lab.qcow2"
  iso_url      = "${var.iso_base_url}/${var.iso_name}"
  iso_checksum = "file:${var.iso_base_url}/SHA256SUMS"

  accelerator    = "kvm"
  cpus           = 4
  memory         = 8192
  disk_size      = "32768M"
  format         = "qcow2"
  disk_interface = "virtio-scsi"
  disk_discard   = "unmap"
  disk_compression = false
  net_device     = "virtio-net"
  headless       = true

  http_directory = "${path.root}/../http"
  boot_wait      = "10s"
  boot_command = [
    "c<wait3>",
    "linux /casper/vmlinuz --- autoinstall ds='nocloud;s=http://{{ .HTTPIP }}:{{ .HTTPPort }}/'<enter><wait3>",
    "initrd /casper/initrd<enter><wait5>",
    "boot<enter>"
  ]

  communicator           = "ssh"
  ssh_username           = var.username
  ssh_password           = var.password
  ssh_timeout            = "90m"
  ssh_handshake_attempts = 1000

  shutdown_command = "echo '${var.password}' | sudo -S shutdown -P now"
  shutdown_timeout = "10m"

  output_directory = "output-qemu"
}

build {
  name    = "devops-lab"
  sources = ["source.qemu.devops_lab"]


  provisioner "shell" {
    execute_command = "echo '${var.password}' | sudo -S env {{ .Vars }} bash '{{ .Path }}'"
    environment_vars = [
      "LAB_USER=${var.username}",
      "DEBIAN_FRONTEND=noninteractive",
      "NEEDRESTART_MODE=a"
    ]
    scripts = ["${path.root}/../scripts/01-base.sh"]
  }


  # Arquivos de apoio (verificar-lab, LEIA-ME)
  provisioner "file" {
    source      = "${path.root}/../files"
    destination = "/tmp"
  }

  provisioner "shell" {
    execute_command = "echo '${var.password}' | sudo -S env {{ .Vars }} bash '{{ .Path }}'"
    environment_vars = [
      "LAB_USER=${var.username}",
      "DEBIAN_FRONTEND=noninteractive",
      "NEEDRESTART_MODE=a"
    ]
    scripts = [
      "${path.root}/../scripts/02-desktop.sh",
      "${path.root}/../scripts/03-devops-tools.sh",
      "${path.root}/../scripts/04-jenkins.sh",
      "${path.root}/../scripts/05-interface.sh",
      "${path.root}/../scripts/06-finalize.sh",
      "${path.root}/../scripts/07-paineis.sh",
      "${path.root}/../scripts/98-enxugar.sh",
      "${path.root}/../scripts/99-cleanup.sh"
    ]
  }
}
