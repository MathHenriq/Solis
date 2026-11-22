# 22/11/2026: os testes automaticos do Solis gravaram os sons sinteticos deles na pasta
# das amostras ao vivo (e o teste de ponta a ponta, a voz Maria). Aqui eles saem pra
# amostras-solis\_dos-testes (movidos, nao apagados: da pra desfazer). Ficam as
# chamadas de verdade do Matheus: as confirmadas de 21/11 13:38-13:39 e os disparos
# do detector de 21/11.
$pasta = Join-Path $env:LOCALAPPDATA 'Solis\voz\amostras-solis'
$destino = Join-Path $pasta '_dos-testes'
$reais = @('vivo-whisper\20261121-133842-100.wav', 'vivo-whisper\20261121-133906-100.wav')
$movidos = 0
foreach ($tipo in 'vivo-whisper', 'vivo-palavra') {
    $p = Join-Path $pasta $tipo
    if (-not (Test-Path $p)) { continue }
    New-Item -ItemType Directory -Force (Join-Path $destino $tipo) | Out-Null
    foreach ($a in Get-ChildItem $p -Filter *.wav) {
        $rel = Join-Path $tipo $a.Name
        $deTeste = $false
        if ($tipo -eq 'vivo-whisper') { $deTeste = -not ($reais -contains $rel) }
        else { $deTeste = $a.Name.StartsWith('20261122') }
        if ($deTeste) {
            Move-Item $a.FullName (Join-Path (Join-Path $destino $tipo) $a.Name)
            $movidos++
        }
    }
}
Write-Output ("movidos pra _dos-testes: {0}" -f $movidos)
foreach ($tipo in 'vivo-whisper', 'vivo-palavra') {
    $p = Join-Path $pasta $tipo
    if (Test-Path $p) { Write-Output ("{0}: ficaram {1}" -f $tipo, (Get-ChildItem $p -Filter *.wav).Count) }
}
# O detector de antes do treino de 22/11 (que aprendeu com os sons dos testes) volta.
$voz = Join-Path $env:LOCALAPPDATA 'Solis\voz\openwakeword'
$antes = Get-ChildItem $voz -Filter 'solis-antes-*.npz' | Sort-Object Name | Select-Object -First 1
if ($antes) {
    Copy-Item (Join-Path $voz 'solis.npz') (Join-Path $voz 'solis-treino-com-testes-20261122.npz') -Force
    Copy-Item $antes.FullName (Join-Path $voz 'solis.npz') -Force
    Write-Output ("detector de volta: {0}" -f $antes.Name)
}
