# Abre o Solis como app (Tauri) em modo de desenvolvimento: o Vite na 1420 e a
# janela nativa por cima dele. O Rust fica em %USERPROFILE%\.cargo\bin, que um
# terminal aberto antes da instalação ainda não tem no PATH.
$env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
Set-Location (Join-Path $PSScriptRoot '..')
npm run tauri dev
