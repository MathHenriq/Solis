# Instala o detector da palavra "Solis" treinado (design/_treino-solis/solis-novo.npz)
# na pasta da voz do Solis, guardando o de antes. Roda no terminal de verdade: o que o
# terminal do Claude grava em %LOCALAPPDATA% não chega ao Windows (a caixa de areia).
param([string]$Novo = "$PSScriptRoot\..\_treino-solis\solis-novo.npz")
$pasta = Join-Path $env:LOCALAPPDATA 'Solis\voz\openwakeword'
$atual = Join-Path $pasta 'solis.npz'
if (-not (Test-Path $Novo)) { Write-Error "não achei o detector novo: $Novo"; exit 1 }
if (Test-Path $atual) {
    $copia = Join-Path $pasta ('solis-antes-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.npz')
    Copy-Item $atual $copia
    Write-Output "o de antes guardado em $copia"
}
Copy-Item $Novo $atual -Force
$h = (Get-FileHash $atual -Algorithm SHA256).Hash.Substring(0, 12)
Write-Output "instalado: $atual ($h). Feche e abra o Solis pra ele carregar."
