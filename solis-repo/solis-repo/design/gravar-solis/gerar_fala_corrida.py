"""Fala corrida pra medir alarme falso (21/11/2026): textos comuns lidos por
vozes do Edge, como uma TV ligada ou uma conversa longa. Nenhum tem "Solis".
Só pra MEDIR (nunca entra no treino). Sai em design/_treino-solis/fala-corrida/
como WAV 16 kHz mono.

Uso: backend\\.venv\\Scripts\\python design\\gravar-solis\\gerar_fala_corrida.py
"""
import asyncio
import io
from pathlib import Path

import numpy as np

DESTINO = Path(__file__).resolve().parents[1] / '_treino-solis' / 'fala-corrida'
VOZES = ['pt-BR-FranciscaNeural', 'pt-BR-AntonioNeural', 'pt-BR-ThalitaMultilingualNeural']
TEXTOS = [
    'Boa noite. O tempo vai mudar no fim de semana em boa parte do país. Uma frente fria chega ao Sul na sexta-feira '
    'e traz chuva forte, com risco de granizo no oeste do Paraná. Em São Paulo, a temperatura cai a partir de sábado, '
    'e a mínima pode chegar a doze graus na capital. No Nordeste, o sol continua firme, com máximas acima de trinta '
    'graus no litoral. Os meteorologistas recomendam atenção a quem vai pegar a estrada.',
    'Pra fazer o bolo, comece separando os ovos. Bata as claras em neve e reserve. Em outra tigela, misture as gemas '
    'com o açúcar até virar um creme clarinho, depois junte o óleo e o suco de laranja. Peneire a farinha com o '
    'fermento e vá incorporando aos poucos, sempre mexendo com calma. Por último, entram as claras, dobrando a massa '
    'devagar pra não perder o ar. Leve ao forno a cento e oitenta graus por uns quarenta minutos.',
    'E começa o segundo tempo aqui no estádio. O time da casa precisa da vitória pra seguir sonhando com a vaga. '
    'Lançamento longo pela direita, o atacante domina, corta o zagueiro e cruza. A bola passa por todo mundo e sai '
    'pela linha de fundo. Que chance! A torcida empurra, canta sem parar, e o técnico pede calma do lado de fora. '
    'Faltam quarenta minutos e o placar ainda está zero a zero.',
    'Oi, tudo bem? Então, eu tava pensando no que a gente conversou ontem. Acho que dá pra viajar em janeiro, sim, '
    'mas a gente precisa ver as passagens logo, porque depois do Natal fica tudo muito caro. Minha irmã falou que '
    'pode ficar com o cachorro. Se você quiser, eu já olho uns hotéis perto da praia e te mando os links mais tarde. '
    'Me avisa o que você acha, tá? Beijo.',
    'A reunião de hoje vai tratar de três assuntos. Primeiro, o orçamento do próximo trimestre, que precisa ser '
    'fechado até a semana que vem. Depois, a contratação de duas pessoas pro time de suporte. E, por fim, os '
    'resultados da pesquisa com os clientes, que mostrou uma melhora grande no atendimento, mas ainda tem reclamação '
    'sobre o tempo de resposta. Quem tiver sugestão pode mandar por escrito até sexta.',
    'Nesta semana, os preços dos alimentos subiram de novo. O tomate ficou vinte por cento mais caro, e o café '
    'continua em alta por causa da seca. Por outro lado, o arroz e o feijão ficaram mais baratos. Os economistas '
    'dizem que a inflação deve desacelerar no começo do ano que vem, mas ainda é cedo pra comemorar. O consumidor '
    'deve pesquisar bastante antes de fazer as compras do mês.',
]


async def mp3(texto, voz):
    import edge_tts
    partes = []
    async for p in edge_tts.Communicate(texto, voz).stream():
        if p['type'] == 'audio':
            partes.append(p['data'])
    return b''.join(partes)


def para_wav16k(dados: bytes, destino: Path):
    import wave

    import av
    c = av.open(io.BytesIO(dados))
    r = av.AudioResampler(format='s16', layout='mono', rate=16000)
    pedacos = []
    for quadro in c.decode(audio=0):
        for q in r.resample(quadro):
            pedacos.append(q.to_ndarray().reshape(-1))
    for q in r.resample(None):
        pedacos.append(q.to_ndarray().reshape(-1))
    pcm = np.concatenate(pedacos).astype(np.int16)
    with wave.open(str(destino), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm.tobytes())
    return len(pcm) / 16000


async def main():
    DESTINO.mkdir(parents=True, exist_ok=True)
    total = 0.0
    for i, texto in enumerate(TEXTOS):
        for voz in VOZES:
            arq = DESTINO / f'{i:02d}-{voz.split("-")[2]}.wav'
            if arq.exists():
                continue
            total += para_wav16k(await mp3(texto, voz), arq)
    print(f'ok: {total / 60:.1f} min novos em {DESTINO}')


asyncio.run(main())
