# DevOps-Lab

Máquina virtual pronta para as aulas de DevOps: é só baixar, importar no VirtualBox e usar.
Também dá para usar direto no navegador, sem instalar nada.

[![Abrir no GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/gabryelcetto/VM-de-devops?quickstart=1)

**Usuário:** `aluno` | **Senha:** `devops` (vale para a VM, o `sudo` e o Jenkins)

## Sumário

1. [O que vem instalado](#1-o-que-vem-instalado)
2. [Opção 1: VirtualBox (baixar a VM)](#2-opção-1-virtualbox-baixar-a-vm)
3. [Opção 2: navegador (sem baixar nada)](#3-opção-2-navegador-sem-baixar-nada)
4. [Primeiros passos](#4-primeiros-passos)
5. [Problemas comuns](#5-problemas-comuns)
6. [Para quem mantém o projeto](#6-para-quem-mantém-o-projeto)

---

## 1. O que vem instalado

| Ferramenta | Detalhes |
|---|---|
| **Ubuntu 24.04 LTS** | Interface XFCE leve, em português, teclado ABNT2; abre a área de trabalho em ~15 s |
| **VS Code** | Em português, com extensões de Python, Docker, Terraform, YAML e Ansible |
| **Docker + Docker Compose** | Funciona sem `sudo` (`docker ...` e `docker compose ...`) |
| **Git** | O terminal mostra a branch atual |
| **Ansible** | Com as coleções `community.general`, `community.docker` e `ansible.posix` |
| **Terraform** | Versão oficial da HashiCorp |
| **Python** | Python 3.12, `pip`, `venv` e `pipx` |
| **Jenkins** | Pronto em `http://localhost:8080`, sem assistente inicial, com plugins de Pipeline, Git, GitHub, Docker e Ansible. Liga sozinho ~1 min após a VM iniciar |
| **Extras** | Firefox com favoritos do Lab, área de transferência entre o PC e a VM, comando `verificar-lab` |

---

## 2. Opção 1: VirtualBox (baixar a VM)

### Requisitos do computador

| Item | Mínimo |
|---|---|
| VirtualBox | 7.x ([download](https://www.virtualbox.org/wiki/Downloads)) |
| Espaço livre em disco | ~8 GB |
| Memória RAM do PC | 8 GB (a VM usa 4 GB) |
| Processador | Intel ou AMD com virtualização ativada (Macs com chip M1/M2/M3 não funcionam) |

### Passo a passo

1. **Baixe a VM** (~1,7 GB, sem login):
   **https://github.com/gabryelcetto/VM-de-devops/releases/latest/download/DevOps-Lab.ova**
2. No VirtualBox, clique em **Arquivo → Importar Appliance**, escolha o `DevOps-Lab.ova` e clique em **Finalizar**.
3. Selecione **DevOps-Lab** e clique em **Iniciar**.
4. Aguarde ~15 s: a VM entra sozinha na área de trabalho.

> **Já tinha uma versão antiga?** Antes de importar a nova, apague a antiga no VirtualBox:
> botão direito em **DevOps-Lab → Remover → Excluir todos os arquivos**.

Cada pessoa que baixa recebe uma cópia própria: o que for feito dentro da VM fica só naquele computador.

---

## 3. Opção 2: navegador (sem baixar nada)

Para quando o PC não deixa instalar programas ou não tem VirtualBox.

1. Clique no botão **Open in GitHub Codespaces** no topo desta página.
2. Entre com sua conta do GitHub e aguarde de 1 a 3 minutos.
3. Abre no navegador um ambiente com as mesmas ferramentas da VM.

| O que | Como acessar |
|---|---|
| Terminal | Menu ☰ → **Terminal → Novo Terminal** |
| Conferir as ferramentas | No terminal: `verificar-lab` |
| Jenkins | Aba **PORTAS** → porta **8080** → 🌐 (senha inicial: comando `senha-jenkins`) |
| Área de trabalho gráfica | Aba **PORTAS** → porta **6080** → 🌐 → **Connect** (senha: `devops`) |

- Cada aluno tem o seu próprio Codespace; o que for feito nele não aparece para os outros.
- Ele desliga sozinho após 30 min parado e é apagado após 30 dias sem uso. Para voltar a ele: <https://github.com/codespaces>
- É gratuito dentro da cota mensal do GitHub (reinicia todo mês). Com o GitHub Student Pack a cota é maior.

---

## 4. Primeiros passos

| Para | Faça |
|---|---|
| Conferir se está tudo funcionando | Abra o **Terminal** e rode `verificar-lab` (tudo deve aparecer como **OK**) |
| Abrir o VS Code, o Firefox ou o Jenkins | Use os
