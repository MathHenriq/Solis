# Aviso do Windows (a notificação no canto da tela), pelo avisos.py.
#
# Pelo PowerShell, como o OCR (ocr_windows.ps1): o pacote de WinRT pro Python
# é bloqueado pelo Controle de Aplicativo do Windows, e o PowerShell é do
# sistema, assinado. Enquanto o Solis não é um app instalado, ele não tem
# identidade própria no Windows (AppUserModelID): o aviso sai em nome do
# PowerShell, com "Solis" na linha de atribuição. Registrar uma identidade
# pede um atalho no menu Iniciar — fica pro app de verdade (Tauri, .msi).
#
# Entrada: JSON pela entrada padrão, {"titulo", "texto", "tag"}. O texto vai
# por nó de XML, nunca colado no XML: título com "<" ou "&" não quebra nada.
# Saída: "ok N", com N avisos desta tag na Central de Notificações (a prova de
# que o Windows recebeu).
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$aviso = [Console]::In.ReadToEnd() | ConvertFrom-Json
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'

$xml = [Windows.Data.Xml.Dom.XmlDocument]::new()
$xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text/><text/><text placement="attribution"/></binding></visual></toast>')
$textos = $xml.GetElementsByTagName('text')
$textos.Item(0).AppendChild($xml.CreateTextNode($aviso.titulo)) | Out-Null
$textos.Item(1).AppendChild($xml.CreateTextNode($aviso.texto)) | Out-Null
$textos.Item(2).AppendChild($xml.CreateTextNode('Solis')) | Out-Null

$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
$toast.Tag = $aviso.tag
$toast.Group = 'solis'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show($toast)

$historico = [Windows.UI.Notifications.ToastNotificationManager]::History.GetHistory($app) | Where-Object { $_.Tag -eq $aviso.tag }
"ok $(@($historico).Count)"
