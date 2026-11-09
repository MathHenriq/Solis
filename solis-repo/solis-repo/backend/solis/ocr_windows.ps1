# OCR do próprio Windows (Windows.Media.Ocr), pela reserva do ocr.py.
#
# Pelo PowerShell, e não por um pacote Python: o pacote de WinRT pro Python traz
# uma DLL sem assinatura, que o Controle de Aplicativo do Windows bloqueia
# (visto no notebook, 09/11/2026). O PowerShell é do sistema e já vem assinado.
#
# A imagem chega em base64 pela entrada padrão, e não num arquivo temporário:
# página de documento privado não passa pelo disco. O texto sai em UTF-8, uma
# linha por linha reconhecida.
param([string]$Lingua = 'pt-BR')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$metodos = [System.WindowsRuntimeSystemExtensions].GetMethods()
$comResultado = ($metodos | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]
function Esperar($operacao, $tipo) {
    $tarefa = $comResultado.MakeGenericMethod($tipo).Invoke($null, @($operacao))
    $tarefa.Wait(-1) | Out-Null
    $tarefa.Result
}

[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.DataWriter, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null

$motor = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($Lingua))
if ($null -eq $motor) { $motor = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if ($null -eq $motor) { [Console]::Error.WriteLine('sem_lingua'); exit 3 }

$bytes = [Convert]::FromBase64String([Console]::In.ReadToEnd())
$fluxo = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
$escritor = [Windows.Storage.Streams.DataWriter]::new($fluxo)
$escritor.WriteBytes($bytes)
Esperar ($escritor.StoreAsync()) ([uint32]) | Out-Null
$escritor.DetachStream() | Out-Null
$fluxo.Seek(0)

$decodificador = Esperar ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($fluxo)) ([Windows.Graphics.Imaging.BitmapDecoder])
$imagem = Esperar ($decodificador.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$resultado = Esperar ($motor.RecognizeAsync($imagem)) ([Windows.Media.Ocr.OcrResult])
foreach ($linha in $resultado.Lines) { $linha.Text }
