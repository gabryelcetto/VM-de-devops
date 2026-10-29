# ==========================================================================
#  DevOps-Lab-UVV - gera output\DevOps-Lab-UVV.ova (Windows)
#  Uso:  powershell -ExecutionPolicy Bypass -File .\build.ps1
#        powershell -ExecutionPolicy Bypass -File .\build.ps1 -Memory 6144 -Cpus 4
# ==========================================================================
param(
    [int]$Cpus = 2,
    [int]$Memory = 4096,
    [switch]$Headless
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "== DevOps-Lab-UVV: preparando build ==" -ForegroundColor Cyan

# --- VirtualBox -----------------------------------------------------------
$vboxDir = Join-Path $env:ProgramFiles "Oracle\VirtualBox"
if (-not (Get-Command VBoxManage -ErrorAction SilentlyContinue)) {
    if (Test-Path (Join-Path $vboxDir "VBoxManage.exe")) {
        $env:Path = "$vboxDir;$env:Path"
    } else {
        Write-Host "VirtualBox nao encontrado. Instale em https://www.virtualbox.org/wiki/Downloads" -ForegroundColor Red
        exit 1
    }
}
Write-Host ("VirtualBox: " + (VBoxManage --version))

# --- Packer ---------------------------------------------------------------
$localPacker = Join-Path $PSScriptRoot "tools"
if (Test-Path (Join-Path $localPacker "packer.exe")) { $env:Path = "$localPacker;$env:Path" }
if (-not (Get-Command packer -ErrorAction SilentlyContinue)) {
    Write-Host "Packer nao encontrado. Baixando a versao oficial da HashiCorp..." -ForegroundColor Yellow
    $ProgressPreference = "SilentlyContinue"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $ver = (Invoke-RestMethod -UseBasicParsing "https://checkpoint-api.hashicorp.com/v1/check/packer").current_version
    $zip = Join-Path $env:TEMP "packer_$ver.zip"
    Invoke-WebRequest -UseBasicParsing -Uri "https://releases.hashicorp.com/packer/$ver/packer_${ver}_windows_amd64.zip" -OutFile $zip
    New-Item -ItemType Directory -Force -Path $localPacker | Out-Null
    Expand-Archive -Force -Path $zip -DestinationPath $localPacker
    $env:Path = "$localPacker;$env:Path"
}
Write-Host ("Packer: " + (packer version | Select-Object -First 1))

# --- Espaco em disco --------------------------------------------------------
$drive = (Get-Item $PSScriptRoot).PSDrive
$freeGB = [math]::Round($drive.Free / 1GB, 1)
Write-Host "Espaco livre em $($drive.Name): $freeGB GB"
if ($freeGB -lt 22) {
    Write-Host "Pouco espaco livre: o build precisa de pelo menos 22 GB livres (o .ova final fica com ate 3,8 GB)." -ForegroundColor Red
    exit 1
}

# --- Descobre a ISO mais recente do Ubuntu 24.04 ---------------------------
$isoName = "ubuntu-24.04.5-live-server-amd64.iso"
try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri "https://releases.ubuntu.com/24.04/SHA256SUMS"
    $text = $resp.Content
    if ($text -is [byte[]]) { $text = [System.Text.Encoding]::ASCII.GetString($text) }
    $m = [regex]::Match($text, "ubuntu-24\.04(\.\d+)*-live-server-amd64\.iso")
    if ($m.Success) { $isoName = $m.Value }
} catch {
    Write-Host "Nao foi possivel consultar a ISO mais recente; usando $isoName" -ForegroundColor Yellow
}
Write-Host "ISO: $isoName"

# --- Build ----------------------------------------------------------------
Write-Host ""
Write-Host "Se o Windows Firewall perguntar, PERMITA o acesso do packer.exe" -ForegroundColor Yellow
Write-Host "(a VM baixa a configuracao de instalacao dele). Leva de 30 a 60 min." -ForegroundColor Yellow
Write-Host ""

$env:PACKER_CACHE_DIR = Join-Path $PSScriptRoot "packer_cache"
packer init .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$headlessValue = if ($Headless) { "true" } else { "false" }
packer build -force `
    -var "iso_name=$isoName" `
    -var "cpus=$Cpus" `
    -var "memory=$Memory" `
    -var "headless=$headlessValue" `
    devops-lab.pkr.hcl
if ($LASTEXITCODE -ne 0) {
    Write-Host "O build falhou. Veja a secao 'Problemas comuns' do README.md" -ForegroundColor Red
    exit $LASTEXITCODE
}

$ova = Join-Path $PSScriptRoot "output\DevOps-Lab-UVV.ova"
$sizeGB = [math]::Round((Get-Item $ova).Length / 1GB, 2)
Write-Host ""
Write-Host "Pronto! Arquivo gerado: $ova ($sizeGB GB)" -ForegroundColor Green
if ($sizeGB -gt 3.8) { Write-Host "ATENCAO: o .ova passou de 3,8 GB." -ForegroundColor Yellow }

# Remove a ISO baixada pelo Packer (3 GB) para devolver espaco ao disco
Remove-Item -Recurse -Force (Join-Path $PSScriptRoot "packer_cache") -ErrorAction SilentlyContinue
Write-Host "Importe no VirtualBox em: Arquivo > Importar Appliance"
