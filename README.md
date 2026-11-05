# DevOps-Lab

Máquina virtual para as aulas de DevOps: é só baixar, importar no VirtualBox e usar.
Também dá para usar direto no navegador, sem instalar nada.

[![Abrir no GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/gabryelcetto/VM-de-devops?quickstart=1)

**Usuário:** `aluno` | **Senha:** `devops` (vale para a VM, o `sudo`, o Jenkins, o Grafana e o Uptime Kuma)

## Sumário

1. [O que vem instalado](#1-o-que-vem-instalado)
2. [Opção 1: VirtualBox (baixar a VM)](#2-opção-1-virtualbox-baixar-a-vm)
3. [Opção 2: navegador (sem baixar nada)](#3-opção-2-navegador-sem-baixar-nada)
4. [Primeiros passos](#4-primeiros-passos)
5. [Painel DevOps](#5-painel-devops)
6. [Monitoramento: Grafana, Prometheus e Uptime Kuma](#6-monitoramento-grafana-prometheus-e-uptime-kuma)
7. [Problemas comuns](#7-problemas-comuns)
8. [Para quem mantém o projeto](#8-para-quem-mantém-o-projeto)

---

## 1. O que vem instalado

| Ferramenta | Detalhes |
|---|---|
| **Ubuntu 24.04 LTS** | Interface XFCE leve, em português, teclado ABNT2; abre a área de trabalho em poucos segundos |
| **VS Code** | Em português, com extensões de Python, Docker, Terraform e YAML |
| **Docker + Docker Compose** | Funciona sem `sudo`. Liga sozinho no primeiro uso (não gasta memória até você usar) |
| **Git** | O terminal mostra a branch atual |
| **Terraform** | Versão oficial da HashiCorp |
| **Python** | Python 3.12, `pip`, `venv` e `pipx` |
| **Jenkins** | Pronto em `http://localhost:8080`, sem assistente inicial, com plugins de Pipeline, Git, GitHub e Docker. Liga sozinho ~1 min após a VM iniciar |
| **Grafana + Prometheus** | Gráficos da própria VM (CPU, memória, disco, rede, containers), prontos para ligar |
| **Uptime Kuma** | Vigia se os serviços do laboratório estão no ar e guarda o histórico |
| **Painel DevOps** | Um painel visual para Docker, Jenkins, Git, VS Code, Terraform, Python e Monitoramento, em `http://localhost:8090` |
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

1. **Baixe a VM** (~1,9 GB, sem login):
   **https://github.com/gabryelcetto/VM-de-devops/releases/latest/download/DevOps-Lab.ova**
2. No VirtualBox, clique em **Arquivo → Importar Appliance**, escolha o `DevOps-Lab.ova` e clique em **Finalizar**.
3. Selecione **DevOps-Lab** e clique em **Iniciar**.
4. Aguarde alguns segundos: a VM entra sozinha na área de trabalho.

> **Usa VirtualBox 6.1?** Baixe o arquivo `DevOps-Lab-compat-vbox6.ova` na
> [página da última versão](https://github.com/gabryelcetto/VM-de-devops/releases/latest).

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
| Abrir o VS Code, o Firefox, o Jenkins ou o Painel DevOps | Use os atalhos da Área de Trabalho ou do painel de baixo |
| Abrir o terminal | `Ctrl + Alt + T` |
| Guardar seus projetos | Use a pasta `~/projetos` (atalho "projetos" na Área de Trabalho) |
| Levar seu trabalho para casa | `git push` para o seu GitHub |
| Trocar a senha | No terminal: `passwd` |

Comandos rápidos:

```bash
code .                     # abre a pasta atual no VS Code
docker run hello-world     # testa o Docker (sem sudo)
docker compose up          # sobe um compose.yaml
terraform init             # inicia um projeto Terraform
python3 -m venv .venv      # cria um ambiente Python
sudo apt install NOME      # instala outro programa
```

---

## 5. Painel DevOps

Abra pelo atalho **Painel DevOps** ou pelo favorito do Firefox (`http://localhost:8090`, só abre dentro da VM).
Tudo com botões e modelos prontos:

| Aba | O que dá para fazer |
|---|---|
| **Docker** | Criar containers a partir de modelos (site, MySQL, PostgreSQL, Redis...), projetos Compose, imagens com Dockerfile, volumes e redes; ver logs e abrir o terminal do container |
| **Jenkins** | Criar Pipeline, Pipeline do Git, Freestyle, Multibranch e Pastas; construir (com parâmetros), ver as etapas e a saída ao vivo, editar o script e os horários, criar credenciais |
| **Git** | Commit escolhendo os arquivos, branches, merge, tag, stash, push, pull, clone; chave SSH e token do GitHub |
| **VS Code** | Abrir projetos e instalar ou remover extensões |
| **Terraform** | init, validate, plan, apply, destroy, **Conferir com a realidade (refresh)** e **Apagar projeto** |
| **Python** | Criar `.venv`, instalar pacotes, rodar scripts e `pytest` |
| **Monitoramento** | Ligar e desligar Grafana, Prometheus e Uptime Kuma com um clique |

> **Apagar um projeto Terraform:** use **⋯ → Apagar projeto** no Painel. Ele roda o `terraform destroy`
> antes de apagar a pasta, então o que o Terraform criou (ex.: um container) some junto.
> Se você apagar a pasta ou o container por fora, o Terraform não fica sabendo; nesse caso use
> **⋯ → Conferir com a realidade (refresh)** para ele atualizar o que existe de verdade.

---

## 6. Monitoramento: Grafana, Prometheus e Uptime Kuma

Ficam **desligados** para não gastar memória. Ligue no **Painel DevOps → aba Monitoramento → Ligar monitoramento**.
As imagens já vêm dentro da VM (não precisa de internet): o **primeiro** "Ligar" leva cerca de 1 minuto
para prepará-las; depois liga em segundos. Ligado, usa cerca de 400 MB de memória.

| Ferramenta | Endereço | Login | Para que serve |
|---|---|---|---|
| **Grafana** | `http://localhost:3000` | `aluno` / `devops` | Gráficos. Já abre no painel **Esta VM** (CPU, memória, disco, rede e containers) |
| **Prometheus** | `http://localhost:9090` | — | Coleta as métricas a cada 15 s e guarda por 2 dias. É de onde o Grafana lê os dados |
| **Uptime Kuma** | `http://localhost:3001` | `aluno` / `devops` | Vigia se Jenkins, Painel, Grafana e Prometheus estão no ar e mostra o histórico |

---

## 7. Problemas comuns

**A janela da VM fica preta**
Baixe o `DevOps-Lab.ova` mais novo (a VM já vem com a controladora de vídeo **VBoxSVGA**).
Numa VM antiga: desligue a VM, vá em **Configurações → Tela → Controladora Gráfica**, escolha **VBoxSVGA**
e ligue de novo (o aviso amarelo de "configuração não recomendada" pode ser ignorado).

**A VM está lenta**
Com a VM desligada, aumente a memória para 6 GB em **Configurações → Sistema**. Desligue o monitoramento
quando não estiver usando (Painel DevOps → aba Monitoramento → Desligar).

**O Jenkins não abre**
Ele liga sozinho cerca de 1 minuto depois que a VM abre. Aguarde e recarregue a página.
Se continuar fora, abra o **Painel DevOps → aba Jenkins** e clique em **Ligar o Jenkins**.

**Erro `VT-x is not available` / `VERR_VMX_NO_VMX`**
Ative a virtualização na BIOS/UEFI do computador. No Windows, se o Hyper-V/WSL2 estiver ativo,
o VirtualBox funciona, mas fica mais lento; para desativar: `bcdedit /set hypervisorlaunchtype off`
(como administrador) e reinicie.

**O Docker diz que a porta já está em uso**
Outro container já usa essa porta. Pare ou apague o outro container na aba Docker do Painel,
ou escolha outra porta (ex.: `8082:80` em vez de `8081:80`).

---

## 8. Para quem mantém o projeto

### Como a VM é gerada e publicada

A cada mudança na branch `main` (ou em **Actions → Run workflow**), o GitHub Actions:

1. monta a VM com **Packer + QEMU/KVM**, usando os scripts de `scripts/`;
2. gera o `.ova` e **testa no VirtualBox de verdade**: importa, liga e confere mais de 100 itens
   (área de trabalho, rede, Docker, Jenkins, Painel DevOps, monitoramento...). Os resultados e prints
   da tela ficam na branch `test-results`;
3. se tudo passar, publica uma **Release** nova com notas automáticas e mantém só as 3 mais recentes.
   O link de download deste README sempre aponta para a última.

### Qualidade (antes de cada versão)

| Verificação | Onde | O que faz |
|---|---|---|
| Checagens rápidas (~10 s) | `bash ci/qa/verificar.sh` | Análise estática (ruff, shellcheck), checa se cada botão da tela chama algo que existe no servidor e roda os testes de unidade do Painel (`tests/`) com cobertura |
| Laboratório do Painel | workflow *Laboratório do Painel* (branch `lab-painel`) | Monta uma cópia da VM e usa o Painel num navegador como o aluno, clicando em todos os modelos e botões; mede o tempo de cada aba e a cobertura de código. Resultados na branch `lab-results` |
| Teste de mutantes | `bash ci/qa/mutantes.sh` (roda junto com o laboratório) | Cria milhares de versões do Painel com um defeito pequeno cada e confere se os testes percebem; falha abaixo de 85% |

As mudanças entram na `main` por **Pull Request**, depois que o laboratório e os testes passam.

### Gerar a VM no seu computador (opcional)

Precisa de **VirtualBox 7.x**, **Packer 1.10+**, processador Intel/AMD com virtualização ativada,
~22 GB livres e 30 a 60 minutos.

```powershell
# Windows (PowerShell, na pasta do projeto)
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

```bash
# Linux / macOS (Intel)
./build.sh
```

O resultado fica em `output/DevOps-Lab.ova`.

### Estrutura

```
VM-de-devops/
├── devops-lab.pkr.hcl        # template Packer (build local com VirtualBox)
├── ci/devops-lab-qemu.pkr.hcl# template Packer do build na nuvem (QEMU/KVM)
├── http/                     # instalação automática do Ubuntu (autoinstall)
├── scripts/                  # instalação: desktop, ferramentas, Jenkins, painéis, monitoramento, limpeza
├── files/painel/             # Painel DevOps (painel.py + index.html)
├── files/monitoramento/      # Grafana, Prometheus e Uptime Kuma (Docker Compose)
├── tests/                    # testes de unidade do Painel
├── ci/                       # testes da VM, laboratório, QA e publicação
└── .devcontainer/            # ambiente do GitHub Codespaces
```




## Licença

Os scripts e arquivos deste projeto estão sob a [licença MIT](LICENSE).
Os programas instalados dentro da VM (Ubuntu, VS Code, Docker, Jenkins, Grafana, Uptime Kuma etc.)
continuam com as licenças de cada um.
