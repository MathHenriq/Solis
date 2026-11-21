# Quem está usando o microfone agora (microfone.py): a cada segundo, os
# programas com uma sessão de captura ATIVA em qualquer microfone do Windows,
# uma linha JSON por mudança ({"outros": ["Discord"]}). Fora: o sistema (pid 0),
# o audiodg e o próprio Solis (o WebView2 dele, que tem com.solis.app na linha
# de comando) e o servidor do Solis (o pid que vem no argumento: desde 21/11/2026
# ele grava o microfone direto, microfone_nativo.py). Pelo PowerShell, como o
# OCR: é do sistema e já vem assinado.
param([int]$PidDoSolis = 0)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumeratorV {}
[ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumeratorV {
  int EnumAudioEndpoints(int flow, int mask, out IMMDeviceCollectionV col);
}
[ComImport, Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceCollectionV { int GetCount(out uint n); int Item(uint i, out IMMDeviceV dev); }
[ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceV { int Activate(ref Guid iid, int ctx, IntPtr p, [MarshalAs(UnmanagedType.IUnknown)] out object o); }
[ComImport, Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioSessionManager2V { int GetAudioSessionControl(); int GetSimpleAudioVolume(); int GetSessionEnumerator(out IAudioSessionEnumeratorV e); }
[ComImport, Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioSessionEnumeratorV { int GetCount(out int n); int GetSession(int i, out IAudioSessionControl2V s); }
[ComImport, Guid("bfb7ff88-7239-4fc9-8fa2-07c950be9c6d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioSessionControl2V {
  int GetState(out int st);
  int GetDisplayName(out IntPtr n); int SetDisplayName(); int GetIconPath(out IntPtr p); int SetIconPath();
  int GetGroupingParam(out Guid g); int SetGroupingParam(); int RegisterAudioSessionNotification(); int UnregisterAudioSessionNotification();
  int GetSessionIdentifier(out IntPtr s); int GetSessionInstanceIdentifier(out IntPtr s);
  int GetProcessId(out uint pid);
}

public static class VigiaMicrofone {
  // Os pids com uma sessão de captura ativa (estado 1), em todos os microfones ligados.
  public static uint[] Ativos() {
    var pids = new List<uint>();
    var en = (IMMDeviceEnumeratorV)new MMDeviceEnumeratorV();
    IMMDeviceCollectionV col; en.EnumAudioEndpoints(1, 1, out col);
    uint n; col.GetCount(out n);
    for (uint i = 0; i < n; i++) {
      IMMDeviceV d; col.Item(i, out d);
      var iid = new Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F");
      object o; d.Activate(ref iid, 23, IntPtr.Zero, out o);
      IAudioSessionEnumeratorV e; ((IAudioSessionManager2V)o).GetSessionEnumerator(out e);
      int k; e.GetCount(out k);
      for (int j = 0; j < k; j++) {
        IAudioSessionControl2V c; e.GetSession(j, out c);
        int st; c.GetState(out st); uint pid; c.GetProcessId(out pid);
        if (st == 1 && pid != 0 && !pids.Contains(pid)) pids.Add(pid);
      }
    }
    return pids.ToArray();
  }
}
'@

$doSolis = @{}
$antes = $null
while ($true) {
    $nomes = @()
    try {
        foreach ($p in [VigiaMicrofone]::Ativos()) {
            $proc = Get-Process -Id $p -ErrorAction SilentlyContinue
            if (-not $proc -or $proc.ProcessName -eq 'audiodg' -or $p -eq $PidDoSolis) { continue }
            if ($proc.ProcessName -eq 'msedgewebview2') {
                if (-not $doSolis.ContainsKey($p)) {
                    $linha = (Get-CimInstance Win32_Process -Filter "ProcessId=$p" -ErrorAction SilentlyContinue).CommandLine
                    $doSolis[$p] = [bool]($linha -match 'com\.solis\.app')
                }
                if ($doSolis[$p]) { continue }
            }
            $nomes += $proc.ProcessName
        }
    } catch {
        # Um aparelho saindo no meio da leitura: vale a próxima volta.
        Start-Sleep -Milliseconds 1000
        continue
    }
    $agora = (@($nomes | Sort-Object -Unique) | ConvertTo-Json -Compress)
    if ($null -eq $agora) { $agora = '[]' }
    if ($agora -notlike '`[*') { $agora = "[$agora]" }
    if ($agora -ne $antes) {
        [Console]::Out.WriteLine('{"outros": ' + $agora + '}')
        [Console]::Out.Flush()
        $antes = $agora
    }
    Start-Sleep -Milliseconds 1000
}
