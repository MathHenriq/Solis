# Lista as amostras ao vivo da palavra "Solis" na pasta de verdade do Windows
# (o terminal do Claude ve tambem o que os testes gravaram na caixa de areia).
$pasta = Join-Path $env:LOCALAPPDATA 'Solis\voz\amostras-solis'
foreach ($tipo in 'vivo-whisper', 'vivo-palavra') {
    $p = Join-Path $pasta $tipo
    if (Test-Path $p) {
        $arquivos = Get-ChildItem $p -Filter *.wav | Sort-Object Name
        Write-Output ("{0} ({1}):" -f $tipo, $arquivos.Count)
        foreach ($a in $arquivos) { Write-Output ("  {0}  {1,7} bytes" -f $a.Name, $a.Length) }
    } else {
        Write-Output ("{0}: nao existe" -f $tipo)
    }
}
