#############################################################################
#  DevOps-Lab-UVV  -  Template Packer para gerar DevOps-Lab-UVV.ova
#
#  Ubuntu 24.04 LTS + XFCE (leve) + VS Code + Docker/Compose + Git +
#  Ansible + Terraform + Python + Jenkins
#
#  Uso:   packer init .   &&   packer build .
#  (ou simplesmente rode build.ps1 no Windows / build.sh no Linux/macOS)
#############################################################################

packer {
  required_version = ">= 1.10.0"
  required_plugins {
    virtualbox = {
      version = ">= 1.1.1"
      source  = "github.com/hashicorp/virtualbox"
    }
  }
}

# --------------------------------------------------------------------------
# Variáveis (podem ser alteradas com -var "nome=valor")
# --------------------------------------------------------------------------
variable "vm_name" {
  type    = string
  default = "DevOps-Lab-UVV"
}

variable "iso_base_url" {
  type    = string
  default = "https://releases.ubuntu.com/24.04"
}

# Os scripts build.ps1/build.sh descobrem automaticamente a ISO mais recente
# do 24.04. Este valor é só o padrão caso você rode o packer manualmente.
variable "iso_name" {
  type    = string
  default = "ubuntu-24.04.5-live-server-amd64.iso"
}

variable "cpus" {
  type    = number
  default = 2
}

variable "memory" {
  type    = number
  default = 4096 # MB
}

variable "disk_size" {
  type    = number
  default = 25600 # MB (disco dinâmico: só ocupa o que for usado)
}

# Precisa bater com o usuário/senha definidos em http/user-data
variable "username" {
  type    = string
  default = "aluno"
}

variable "password" {
  type      = string
  default   = "devops"
  sensitive = true
}

variable "headless" {
  type    = bool
  default = false # false = mostra a janela da VM durante a instalação
}

# --------------------------------------------------------------------------
# Builder VirtualBox
# --------------------------------------------------------------------------
source "virtualbox-iso" "devops_lab" {
  vm_name       = var.vm_name
  guest_os_type = "Ubuntu_64"

  iso_url      = "${var.iso_base_url}/${var.iso_name}"
  iso_checksum = "file:${var.iso_base_url}/SHA256SUMS"

  cpus                     = var.cpus
  memory                   = var.memory
  disk_size                = var.disk_size
  hard_drive_interface     = "sata"
  hard_drive_discard       = true
  hard_drive_nonrotational = true
  iso_interface            = "sata"
  gfx_controller           = "vmsvga"
  gfx_vram_size            = 128
  headless                 = var.headless

  # Guest Additions vêm dos pacotes do Ubuntu (virtualbox-guest-utils/x11)
  guest_additions_mode = "disable"

  # Instalação 100% automática (Ubuntu autoinstall via HTTP do Packer)
  http_directory = "http"
  boot_wait      = "8s"
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

  vboxmanage = [
    ["modifyvm", "{{ .Name }}", "--clipboard-mode", "bidirectional"],
    ["modifyvm", "{{ .Name }}", "--draganddrop", "bidirectional"],
    ["modifyvm", "{{ .Name }}", "--mouse", "usbtablet"]
  ]

  # Exporta direto como .ova
  format           = "ova"
  output_directory = "output"
  output_filename  = var.vm_name
  export_opts = [
    "--manifest",
    "--vsys", "0",
    "--product", "DevOps Lab UVV",
    "--version", "1.0",
    "--description", "Ubuntu 24.04 LTS + XFCE com VS Code, Docker, Docker Compose, Git, Ansible, Terraform, Python e Jenkins. Usuario: aluno / Senha: devops"
  ]
}

# --------------------------------------------------------------------------
# Provisionamento
# --------------------------------------------------------------------------
build {
  name    = "devops-lab-uvv"
  sources = ["source.virtualbox-iso.devops_lab"]


  provisioner "shell" {
    execute_command = "echo '${var.password}' | sudo -S env {{ .Vars }} bash '{{ .Path }}'"
    environment_vars = [
      "LAB_USER=${var.username}",
      "DEBIAN_FRONTEND=noninteractive",
      "NEEDRESTART_MODE=a"
    ]
    scripts = ["scripts/01-base.sh"]
  }


  # Arquivos de apoio (verificar-lab, LEIA-ME)
  provisioner "file" {
    source      = "files"
    destination = "/tmp"
  }

  provisioner "shell" {
    execute_command = "echo '${var.password}' | sudo -S env {{ .Vars }} bash '{{ .Path }}'"
    environment_vars = [
      "LAB_USER=${var.username}",
      "DEBIAN_FRONTEND=noninteractive",
      "NEEDRESTART_MODE=a"
    ]
    expect_disconnect = false
    scripts = [
      "scripts/02-desktop.sh",
      "scripts/03-devops-tools.sh",
      "scripts/04-jenkins.sh",
      "scripts/05-finalize.sh",
      "scripts/99-cleanup.sh"
    ]
  }

  post-processor "checksum" {
    checksum_types = ["sha256"]
    output         = "output/DevOps-Lab-UVV.ova.{{ .ChecksumType }}"
  }
}
