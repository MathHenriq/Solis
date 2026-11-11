# Prepara a voz local na GPU: um ambiente Python separado (3.11, o que as
# bibliotecas de voz aceitam) com o PyTorch para CUDA e as vozes candidatas.
# Separado do backend/.venv de propósito: o PyTorch é pesado e fixa versões de
# bibliotecas que o resto do Solis não precisa.
#
# Precisa do Controle Inteligente de Aplicativos desligado (o PyTorch carrega
# DLLs que ele bloqueava) e de uns 10 GB livres.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..\backend')
$py = '.venv-voz\Scripts\python.exe'

if (-not (Test-Path $py)) { uv venv .venv-voz --python 3.11 }
uv pip install --python $py torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
uv pip install --python $py chatterbox-tts
# A marca d'água da Resemble (perth) usa o pkg_resources, que o setuptools 81 tirou.
uv pip install --python $py "setuptools<81"
& $py -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
