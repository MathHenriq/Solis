#!/usr/bin/env bash
# O instalador do Solis como servidor: o cérebro na nuvem (26/11/2026).
#
# Num Ubuntu ou Debian limpo, como root. Um comando monta tudo, e rodar de novo
# atualiza (o código, as bibliotecas, a tela) sem perder o banco, a senha nem
# as chaves:
#
#   curl -fsSL https://raw.githubusercontent.com/MathHenriq/Solis/main/solis-repo/solis-repo/backend/instalar_servidor.sh | sudo bash
#
# O que fica onde:
#   /var/lib/solis                    a casa do usuário solis (sem login)
#   /var/lib/solis/codigo             o repositório (só a parte do app)
#   /var/lib/solis/.local/share/solis o banco (solis.db) e a senha (token)
#   /var/lib/solis/.config/solis      a chave do cofre, longe do banco
#   /var/lib/solis/Solis/whisper      o Whisper pequeno (o cadeado: a fala fica aqui)
#   /var/lib/solis/Solis/voz/kokoro   a voz local (a resposta privada falada)
#   solis.service                     liga sozinho, volta se cair; só em 127.0.0.1
#
# O endereço com https (o celular, o microfone, os avisos) vem depois, pela
# Tailscale: o fim deste script diz os três comandos.
#
# Variáveis (opcionais): SOLIS_RAMO (main), SOLIS_PORTA (8765), SOLIS_SEM_MODELOS=1
# (pula os modelos de voz), SOLIS_CODIGO_DE=<pasta> (copia de uma cópia local do
# app em vez de clonar; é como o teste no GitHub roda).
set -euo pipefail

REPO=${SOLIS_REPO:-https://github.com/MathHenriq/Solis.git}
RAMO=${SOLIS_RAMO:-main}
PORTA=${SOLIS_PORTA:-8765}
CASA=/var/lib/solis
CODIGO=$CASA/codigo
APP=$CODIGO/solis-repo/solis-repo
WHISPER=$CASA/Solis/whisper/faster-whisper-small
KOKORO=$CASA/Solis/voz/kokoro
KOKORO_URL=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0

passo() { printf '\n== %s\n' "$*"; }
como_solis() { runuser -u solis -- env HOME="$CASA" PATH="/usr/local/bin:/usr/bin:/bin" bash -c "$*"; }

[ "$(id -u)" = 0 ] || { echo 'Rode como root: sudo bash instalar_servidor.sh'; exit 1; }
command -v apt-get >/dev/null || { echo 'Este instalador é pra Ubuntu ou Debian (apt).'; exit 1; }
inicio=$(date +%s)

passo 'Pacotes do sistema'
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl ca-certificates rsync >/dev/null

passo 'Node (pra construir a tela)'
if ! command -v node >/dev/null || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 20 ]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null
  apt-get install -y -qq nodejs >/dev/null
fi
node --version

passo 'uv (o Python 3.14 do Solis, sem mexer no Python do sistema)'
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh >/dev/null
uv --version

passo 'O usuário solis'
id solis >/dev/null 2>&1 || useradd --system --create-home --home-dir "$CASA" --shell /usr/sbin/nologin solis
chmod 750 "$CASA"

passo 'O código'
if [ -n "${SOLIS_CODIGO_DE:-}" ]; then
  mkdir -p "$APP"
  rsync -a --delete --exclude node_modules --exclude dist --exclude backend/.venv --exclude src-tauri/target \
    "$SOLIS_CODIGO_DE/" "$APP/"
  chown -R solis:solis "$CODIGO"
elif [ -d "$CODIGO/.git" ]; then
  como_solis "git -C '$CODIGO' fetch -q origin '$RAMO' && git -C '$CODIGO' reset -q --hard 'origin/$RAMO'"
else
  install -d -o solis -g solis "$CODIGO"
  como_solis "git clone -q --depth 1 --branch '$RAMO' --filter=blob:none --sparse '$REPO' '$CODIGO' && git -C '$CODIGO' sparse-checkout set solis-repo/solis-repo"
fi

passo 'As bibliotecas do servidor (Python 3.14)'
como_solis "cd '$APP/backend' && uv python install -q 3.14 && ([ -x .venv/bin/python ] || uv venv -q --seed --python 3.14 .venv) \
  && .venv/bin/python -m pip install -q -r requirements.txt -r requirements-dev.txt \
  && .venv/bin/python -m pip install -q --ignore-requires-python -r requirements-fala.txt"

passo 'A tela (o celular abre o Solis por ela)'
como_solis "cd '$APP' && npm ci --no-audit --no-fund --loglevel=error >/dev/null && npm run build >/dev/null"
[ -f "$APP/dist/index.html" ] && echo 'construída'

if [ "${SOLIS_SEM_MODELOS:-0}" != 1 ]; then
  passo 'O Whisper pequeno (a fala com o cadeado é transcrita aqui)'
  if [ ! -f "$WHISPER/model.bin" ]; then
    como_solis "'$APP/backend/.venv/bin/python' -c \"from faster_whisper.utils import download_model; download_model('small', output_dir='$WHISPER')\""
  fi
  du -sh "$WHISPER" | cut -f1

  passo 'A voz local, Kokoro (a resposta privada sai falada)'
  como_solis "mkdir -p '$KOKORO'"
  for f in kokoro-v1.0.int8.onnx voices-v1.0.bin; do
    [ -s "$KOKORO/$f" ] || como_solis "curl -fsSL -o '$KOKORO/$f.parte' '$KOKORO_URL/$f' && mv '$KOKORO/$f.parte' '$KOKORO/$f'"
  done
  du -sh "$KOKORO" | cut -f1
fi

passo 'O serviço'
cat > /etc/systemd/system/solis.service <<EOF
[Unit]
Description=Solis, o cérebro na nuvem
After=network-online.target
Wants=network-online.target

[Service]
User=solis
Group=solis
WorkingDirectory=$APP/backend
Environment=HOME=$CASA
Environment=SOLIS_SERVIDOR=1
ExecStart=$APP/backend/.venv/bin/python -m uvicorn solis.main:app --host 127.0.0.1 --port $PORTA
Restart=always
RestartSec=3
# Só o que ele precisa: a casa dele pra escrever, o resto do sistema só pra ler.
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$CASA
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable -q solis
systemctl restart solis

for _ in $(seq 1 60); do
  curl -sf "http://127.0.0.1:$PORTA/saude" >/dev/null && break
  sleep 1
done
curl -sf "http://127.0.0.1:$PORTA/saude" >/dev/null || { echo 'O Solis não subiu. O log: journalctl -u solis -n 50'; exit 1; }
TOKEN=$CASA/.local/share/solis/token

passo "Pronto em $(( $(date +%s) - inicio )) s"
cat <<EOF
O Solis está no ar em http://127.0.0.1:$PORTA (só dentro desta máquina).

A senha (o token) pra entrar pelo celular:
  sudo cat $TOKEN

O endereço com https pro celular (a Tailscale, grátis no uso pessoal):
  curl -fsSL https://tailscale.com/install.sh | sh
  sudo tailscale up
  sudo tailscale serve --bg $PORTA
No celular: o app da Tailscale, a mesma conta, e abrir o endereço que o último comando mostrar.

Atualizar depois: rodar este mesmo comando de novo. O log: journalctl -u solis -f
EOF
