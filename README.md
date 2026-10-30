# DevOps-Lab

## Baixar a VM (sem login, direto pelo navegador)

**https://github.com/gabryelcetto/VM-de-devops/releases/latest/download/DevOps-Lab.ova**

1. Baixe o arquivo pelo link acima (~1,7 GB).
2. No VirtualBox: **Arquivo → Importar Appliance** → escolha o `.ova` → **Finalizar**.
3. Inicie a VM. Usuário **aluno**, senha **devops** (veja [CREDENCIAIS.txt](CREDENCIAIS.txt)).

Cada pessoa que baixa recebe uma cópia própria: o que for feito dentro da VM fica só naquele computador.

> VirtualBox antigo (6.1) e o arquivo não importa? Use o `DevOps-Lab-compat-vbox6.ova`, na mesma
> [página de Releases](https://github.com/gabryelcetto/VM-de-devops/releases/latest).
> Depois de importar esse arquivo, vá em Configurações → Tela → Controladora Gráfica e escolha
> **VBoxSVGA** (senão a janela da VM pode ficar preta).
>
> Para rodar, o PC precisa de ~8 GB livres em disco. A VM usa 4 GB de RAM e 2 CPUs.
> Com o Hyper-V do Windows ligado (ícone de tartaruga verde no VirtualBox) ela funciona, mas fica mais lenta.

##  Usar direto no navegador (sem baixar nada)

[![Abrir no GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/gabryelcetto/VM-de-devops?quickstart=1)

Clique no botão acima, entre com sua conta do GitHub e aguarde 1–3 minutos. Abre no navegador
um ambiente com as mesmas ferramentas da VM: **VS Code, Docker + Docker Compose, Git, Ansible,
Terraform, Python e Jenkins**. Não precisa de VirtualBox, cmd, PowerShell nem permissão de administrador.

| O que | Como acessar |
|---|---|
| Terminal | Menu ☰ → **Terminal → Novo Terminal** |
| Conferir tudo | No terminal: `verificar-lab` |
| Jenkins | Aba **PORTAS** → porta **8080** → 🌐 (senha inicial: comando `senha-jenkins`) |
| Área de trabalho gráfica | Aba **PORTAS** → porta **6080** → 🌐 → **Connect** (senha: `devops`) |

- Cada aluno tem o seu próprio Codespace; o que for feito nele não aparece para os outros.
- O Codespace desliga sozinho após 30 min parado e é apagado após 30 dias sem uso. Para voltar: <https://github.com/codespaces>
- O uso é gratuito dentro da cota mensal da conta do GitHub (que reinicia todo mês); alunos com o GitHub Student Pack têm cota maior. Apague o Codespace quando não for mais usar.

Projeto que gera automaticamente a máquina virtual **`DevOps-Lab.ova`** para o
Oracle VirtualBox, com:

| Item | Detalhe |
|---|---|
| Sistema | Ubuntu 24.04 LTS, kernel enxuto para VM, boot silencioso (~20 s até a área de trabalho) |
| Interface | XFCE leve com painel embaixo (menu, Arquivos, Terminal, Firefox, VS Code, Jenkins), atalhos na Área de Trabalho, papel de parede próprio, fonte Ubuntu, pt-BR e teclado ABNT2 |
| VS Code | Em português, com extensões de Python, Docker, Terraform, YAML e Ansible; sem telemetria e sem avisos de chaveiro |
| Docker + Docker Compose | Docker CE oficial (liga no primeiro uso), `docker compose` e atalho `docker-compose`, logs com tamanho limitado |
| Git | Prompt do terminal mostra a branch atual |
| Ansible | `ansible-core` + coleções `community.general`, `community.docker` e `ansible.posix` |
| Terraform | Repositório oficial da HashiCorp |
| Python | Python 3.12, `pip`, `venv`, `pipx` |
| Jenkins | LTS pronto para uso: usuário **aluno/devops**, sem assistente inicial, plugins de Pipeline, Git, GitHub, Docker e Ansible já instalados; liga ~1 min após o boot |
| Extras | Firefox com página inicial do Lab e favoritos, Guest Additions, área de transferência e arrastar/soltar, comando `verificar-lab` |

**Login da VM:** usuário `aluno`, senha `devops`.
A senha inicial do Jenkins fica no arquivo `LEIA-ME.txt` na Área de Trabalho da VM.

---

## Opção A – Gerar na nuvem (GitHub Actions, sem usar espaço do seu PC)

A cada push na branch `main` (ou em **Actions → Run workflow**) o GitHub:

1. monta a VM com Packer + QEMU/KVM;
2. converte para `.ova` e **testa no VirtualBox de verdade** (importa, liga, confere área de trabalho,
   rede, Docker, Jenkins e as ferramentas; prints da tela ficam na branch `test-results`);
3. se o teste passar, publica uma **Release** nova — o link de download acima passa a apontar para ela.

O build na nuvem usa QEMU/KVM (`ci/devops-lab-qemu.pkr.hcl`) com os mesmos scripts de instalação
e converte o disco para `.ova` do VirtualBox (`ci/make-ova.py`).

## Opção B – Gerar no seu computador

## 1. Pré-requisitos (no seu computador)

- **VirtualBox 7.x** – <https://www.virtualbox.org/wiki/Downloads>
- **Packer 1.10 ou superior**
  - Windows: `winget install --id Hashicorp.Packer -e`
  - Ubuntu/Debian: <https://developer.hashicorp.com/packer/install>
- Processador **x86-64** (Intel/AMD) com virtualização (VT-x/AMD-V) ativada na BIOS
  — Macs com chip Apple (M1/M2/M3…) não rodam esta VM
- ~**22 GB livres** em disco durante o build (o `.ova` final fica com ~1,7 GB) e conexão com a internet
- Tempo estimado: **30 a 60 minutos**

## 2. Gerar o .ova

### Windows
Abra o PowerShell na pasta do projeto e rode:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

Opcional: `-Cpus 4 -Memory 6144` para um build mais rápido, `-Headless` para não mostrar a janela da VM.

> Quando o Windows Firewall perguntar, **permita** o `packer.exe`. A VM baixa dele a
> configuração da instalação automática.

### Linux / macOS (Intel)

```bash
chmod +x build.sh
./build.sh
# ou: CPUS=4 MEMORY=6144 HEADLESS=true ./build.sh
```

Uma janela do VirtualBox vai abrir e você verá o Ubuntu se instalando sozinho.
**Não digite nada nela.** Ao final aparece:

```
output/DevOps-Lab.ova
output/DevOps-Lab.ova.sha256
```

## 3. Importar e usar

1. VirtualBox → **Arquivo → Importar Appliance** → selecione `DevOps-Lab.ova`.
2. Em "Política de endereço MAC", deixe **Gerar novos endereços MAC**.
3. Inicie a VM. Ela entra direto no XFCE.
4. Abra o Terminal e rode `verificar-lab` para conferir todas as ferramentas.
5. Jenkins: abra o Firefox em `http://localhost:8080` e use a senha do `LEIA-ME.txt`.

O mesmo `.ova` pode ser copiado para outros colegas/laboratórios. Cada VM importada
gera um machine-id e chaves SSH próprias no primeiro boot.

Recomendado: 4 GB de RAM no mínimo; 6–8 GB se for usar Jenkins + Docker + VS Code juntos.

## 4. Personalizar

| O que | Onde |
|---|---|
| CPUs, memória, tamanho do disco | variáveis no topo de `devops-lab.pkr.hcl` |
| Usuário, senha, hostname, fuso, idioma, teclado | `http/user-data` (a senha também em `devops-lab.pkr.hcl`) |
| Programas instalados | `scripts/01-base.sh` … `scripts/04-jenkins.sh` |
| Texto da Área de Trabalho | `files/LEIA-ME.txt` |

Para trocar a senha: gere o hash com `openssl passwd -6 'NovaSenha'`, coloque em
`http/user-data` (campo `password`) e altere a variável `password` em `devops-lab.pkr.hcl`.

## 5. Problemas comuns

**A janela da VM fica preta**
Baixe o `DevOps-Lab.ova` mais novo (desde 30/10/2026 a VM já vem com a controladora
de vídeo **VBoxSVGA**, que resolve isso). Numa VM importada antes dessa data: desligue a VM,
vá em Configurações → Tela → Controladora Gráfica, escolha **VBoxSVGA** e ligue de novo
(o aviso amarelo de "configuração não recomendada" pode ser ignorado).

**Fica muito tempo em "Waiting for SSH to become available…"**
É normal esperar 15–30 min (o Ubuntu está sendo instalado). Se passar de 60 min, olhe a
janela da VM:
- Se ela parou no menu do instalador pedindo idioma, a VM não conseguiu baixar a
  configuração: libere o `packer.exe` no firewall (Windows) e rode de novo.
- Se ela ficou na tela do GRUB com o texto digitado pela metade, o computador demorou
  para dar boot: aumente `boot_wait` (ex.: `"15s"`) em `devops-lab.pkr.hcl`.

**Erro `VT-x is not available` / `VERR_VMX_NO_VMX`**
Ative a virtualização na BIOS/UEFI. No Windows, se o Hyper-V/WSL2 estiver ativo, o
VirtualBox funciona, mas bem mais lento; para desativar:
`bcdedit /set hypervisorlaunchtype off` (como administrador) e reinicie.

**Erro de checksum da ISO**
Saiu uma nova versão do 24.04. Os scripts `build.ps1`/`build.sh` já pegam a mais
recente; se rodar o `packer` direto, informe `-var "iso_name=ubuntu-24.04.X-live-server-amd64.iso"`.

**"output directory already exists"**
Os scripts usam `-force` e sobrescrevem a pasta `output`. Mova seu `.ova` antigo antes, se quiser guardá-lo.

**Falha ao baixar pacotes (Docker, HashiCorp, Jenkins, Microsoft)**
Normalmente é rede instável ou proxy da instituição. Rode o build de novo; se estiver
atrás de proxy, rode em uma rede sem bloqueio.

## Estrutura

```
DevOps-Lab/
├── devops-lab.pkr.hcl      # template Packer (VM, instalação, exportação .ova)
├── build.ps1 / build.sh    # scripts de um comando
├── http/user-data          # instalação automática do Ubuntu (autoinstall)
├── http/meta-data
├── scripts/                # provisionamento (desktop, ferramentas, Jenkins, limpeza)
└── files/                  # verificar-lab e LEIA-ME da Área de Trabalho
```
