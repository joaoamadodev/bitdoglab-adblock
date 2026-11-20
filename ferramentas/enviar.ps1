# Envia os arquivos do projeto para a BitDogLab (MicroPython) via mpremote.
# Uso:  powershell -ExecutionPolicy Bypass -File ferramentas\enviar.ps1
# Pré-requisito: python -m pip install --user mpremote   (feito uma vez)

$ErrorActionPreference = "Stop"
$fw = Join-Path $PSScriptRoot "..\firmware"
Set-Location $fw

if (-not (Test-Path "config.py")) {
  Write-Host "Falta o config.py. Copie o config.exemplo.py e preencha." -ForegroundColor Red
  exit 1
}

Write-Host "Placas conectadas:" -ForegroundColor Cyan
python -m mpremote connect list

$apoio = @("config.py","dns.py","lista.py","painel.py","web.py","liberar.txt","bloquear.txt","bloqueio.bin")
Write-Host "`nEnviando arquivos de apoio..." -ForegroundColor Cyan
python -m mpremote cp @apoio :

Write-Host "Enviando main.py..." -ForegroundColor Cyan
python -m mpremote cp main.py :

Write-Host "`nArquivos na placa:" -ForegroundColor Cyan
python -m mpremote ls

Write-Host "`nReiniciando a placa..." -ForegroundColor Cyan
python -m mpremote reset
Write-Host "Pronto. O AdBlock vai subir em alguns segundos." -ForegroundColor Green
