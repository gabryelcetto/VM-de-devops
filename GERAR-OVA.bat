@echo off
chcp 65001 >nul
title DevOps-Lab-UVV - gerando o .ova (nao feche esta janela)
cd /d "%~dp0"
echo Gerando DevOps-Lab-UVV.ova. Isso leva de 30 a 60 minutos.
echo O log completo fica em build.log
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { $env:PACKER_LOG='0'; & '.\build.ps1' -Cpus 2 -Memory 4096 *>&1 | Tee-Object -FilePath '.\build.log'; exit $LASTEXITCODE }"
echo.
if exist "output\DevOps-Lab-UVV.ova" (
  echo PRONTO: %~dp0output\DevOps-Lab-UVV.ova
  echo FIM-OK>> build.log
) else (
  echo O build falhou. Veja build.log
  echo FIM-ERRO>> build.log
)
pause
