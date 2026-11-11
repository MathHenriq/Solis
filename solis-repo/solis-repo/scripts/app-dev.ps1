# Abre o Solis como app (Tauri) em modo de desenvolvimento: o Vite na 1420 e a
# janela nativa por cima dele. O Rust fica em %USERPROFILE%\.cargo\bin, que um
# terminal aberto antes da instalação ainda não tem no PATH.
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
# Só em desenvolvimento: a porta de depuração do WebView2, pra testar o app por
# fora (Playwright via CDP) sem microfone nem modelo. Fica só em 127.0.0.1.
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = '--remote-debugging-port=9333'
Set-Location (Join-Path $PSScriptRoot '..')
npm run tauri dev
