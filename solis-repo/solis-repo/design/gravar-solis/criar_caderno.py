"""Gera o caderno do Colab (design/gravar-solis/treinar-solis.ipynb) que treina a
palavra "Solis" no openWakeWord com o pacote do Solis (montar_pacote.py): as
vozes em português, as gravações do Matheus e os negativos parecidos. Baseado no
caderno oficial (notebooks/automatic_model_training.ipynb), sem o gerador de
vozes em inglês (Piper), que pode não instalar no Colab de hoje e que aqui não
faz falta: as pastas já chegam cheias.

Uso: backend/.venv/Scripts/python design/gravar-solis/criar_caderno.py
"""
import json
from pathlib import Path

CELULAS = [
    ('markdown', """# Treinar o "Solis" (openWakeWord)
Antes: **Ambiente de execução → Alterar o tipo de ambiente de execução → GPU T4**.
Depois: **Ambiente de execução → Executar tudo**. Na célula 3, escolha o `solis-treino.zip`.
No fim, o `solis.onnx` baixa sozinho. Leva perto de 1 hora."""),
    ('code', """# 1. A placa de vídeo do Colab
!nvidia-smi -L"""),
    ('code', """# 2. O treinador do openWakeWord e o que ele usa
!git clone -q https://github.com/dscripka/openWakeWord
!pip install -q -e ./openWakeWord
!pip install -q pronouncing audiomentations==0.33.0 torch-audiomentations==0.11.0 acoustics mutagen speechbrain "datasets<4" torchinfo torchmetrics
!pip install -q torchcodec || true
import os
os.makedirs('./openWakeWord/openwakeword/resources/models', exist_ok=True)
for n in ['embedding_model.onnx', 'melspectrogram.onnx']:
    !wget -q https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/{n} -O ./openWakeWord/openwakeword/resources/models/{n}
# O train.py importa o gerador de vozes (Piper) logo no começo, mesmo sem usar.
# Aqui as vozes vêm do pacote do Solis: um substituto vazio no lugar.
os.makedirs('sem_piper', exist_ok=True)
open('sem_piper/generate_samples.py', 'w').write(
    'def generate_samples(*a, **k):\\n    raise RuntimeError("as vozes vêm do pacote do Solis")\\n')
print('ok')"""),
    ('code', """# 3. O pacote do Solis: escolha o solis-treino.zip
from google.colab import files
enviado = files.upload()
!mkdir -p my_custom_model/solis && unzip -q -o solis-treino.zip -d my_custom_model/solis
for p in ['positive_train', 'positive_test', 'negative_train', 'negative_test']:
    print(p, len(os.listdir(f'my_custom_model/solis/{p}')))"""),
    ('code', """# 4. Eco de sala e barulho de fundo (os mesmos do caderno oficial)
import numpy as np, scipy.io.wavfile, datasets
from pathlib import Path
from tqdm import tqdm
os.makedirs('mit_rirs', exist_ok=True)
for row in tqdm(datasets.load_dataset('davidscripka/MIT_environmental_impulse_responses', split='train', streaming=True)):
    nome = row['audio']['path'].split('/')[-1]
    scipy.io.wavfile.write(f'mit_rirs/{nome}', 16000, (row['audio']['array'] * 32767).astype(np.int16))
os.makedirs('audioset', exist_ok=True)
!wget -q -O audioset/bal_train09.tar https://huggingface.co/datasets/agkphysics/AudioSet/resolve/main/data/bal_train09.tar
!cd audioset && tar -xf bal_train09.tar
os.makedirs('audioset_16k', exist_ok=True)
ds = datasets.Dataset.from_dict({'audio': [str(i) for i in Path('audioset/audio').glob('**/*.flac')]})
ds = ds.cast_column('audio', datasets.Audio(sampling_rate=16000))
for row in tqdm(ds):
    nome = row['audio']['path'].split('/')[-1].replace('.flac', '.wav')
    scipy.io.wavfile.write(f'audioset_16k/{nome}', 16000, (row['audio']['array'] * 32767).astype(np.int16))
os.makedirs('fma', exist_ok=True)
fma = datasets.load_dataset('rudraml/fma', name='small', split='train', streaming=True)
fma = iter(fma.cast_column('audio', datasets.Audio(sampling_rate=16000)))
for i in tqdm(range(120)):  # 1 hora de música (clipes de 30 s)
    row = next(fma)
    nome = row['audio']['path'].split('/')[-1].replace('.mp3', '.wav')
    scipy.io.wavfile.write(f'fma/{nome}', 16000, (row['audio']['array'] * 32767).astype(np.int16))
print('ok')"""),
    ('code', """# 5. Os negativos prontos: ~2.000 h de áudio comum e ~11 h pra medir o "acordou sozinho"
!wget -q https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/openwakeword_features_ACAV100M_2000_hrs_16bit.npy
!wget -q https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/validation_set_features.npy
!ls -lh *.npy"""),
    ('code', """# 6. A configuração do treino
import yaml
config = yaml.load(open('openWakeWord/examples/custom_model.yml').read(), yaml.Loader)
config['target_phrase'] = ['solis']
config['model_name'] = 'solis'
config['n_samples'] = len(os.listdir('my_custom_model/solis/positive_train'))
config['n_samples_val'] = len(os.listdir('my_custom_model/solis/positive_test'))
config['steps'] = 20000
config['piper_sample_generator_path'] = './sem_piper'
config['output_dir'] = './my_custom_model'
config['rir_paths'] = ['./mit_rirs']
config['background_paths'] = ['./audioset_16k', './fma']
config['background_paths_duplication_rate'] = [1, 1]
config['false_positive_validation_data_path'] = 'validation_set_features.npy'
config['feature_data_files'] = {'ACAV100M_sample': 'openwakeword_features_ACAV100M_2000_hrs_16bit.npy'}
yaml.dump(config, open('solis.yaml', 'w'))
print({k: config[k] for k in ['target_phrase', 'n_samples', 'n_samples_val', 'steps']})"""),
    ('code', """# 7. Aumentar os exemplos (eco de sala, barulho) e calcular o que o modelo vê
!python openWakeWord/openwakeword/train.py --training_config solis.yaml --augment_clips"""),
    ('code', """# 8. Treinar (a parte demorada)
!python openWakeWord/openwakeword/train.py --training_config solis.yaml --train_model"""),
    ('code', """# 9. Baixar o modelo pro PC
files.download('my_custom_model/solis.onnx')"""),
]


def celula(tipo: str, texto: str) -> dict:
    base = {'cell_type': tipo, 'metadata': {}, 'source': texto.splitlines(keepends=True)}
    if tipo == 'code':
        base.update(execution_count=None, outputs=[])
    return base


caderno = {
    'nbformat': 4, 'nbformat_minor': 0,
    'metadata': {'accelerator': 'GPU', 'colab': {'provenance': [], 'gpuType': 'T4'},
                 'kernelspec': {'name': 'python3', 'display_name': 'Python 3'}},
    'cells': [celula(t, s) for t, s in CELULAS],
}
destino = Path(__file__).with_name('treinar-solis.ipynb')
destino.write_text(json.dumps(caderno, ensure_ascii=False, indent=1), encoding='utf-8')
print(destino)
