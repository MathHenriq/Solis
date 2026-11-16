"""O teste de qualidade da escuta (docs/IDEIAS.md: "voz é a prioridade nº 1;
só existe o que funciona, com a taxa de sucesso medida").

O Matheus grava uns 3 minutos e meio seguindo um roteiro na tela (Configurações
→ Voz → Testar a escuta): chamadas de verdade ("Solis, que horas são?",
baixinho, de longe, com pausa) e trechos sem "Solis" (fala normal, palavras
parecidas, silêncio). Como o roteiro diz o que foi falado e quando, a medida é
exata. A gravação fica só no PC (pasta voz-teste, ao lado do banco).

Medir roda a escuta sobre a gravação, quadro a quadro, do mesmo jeito que ela
roda ao vivo (o laço do WebSocket /escuta, em main.py), e conta: quantas
chamadas acordaram, quantas viraram o pedido certo, quanto tempo do fim da fala
até o texto, e quantos alarmes falsos. O fim da fala de cada chamada vem do
Silero VAD (outro detector, pra medida não depender da peça medida)."""
from __future__ import annotations

import array
import asyncio
import difflib
import io
import json
import logging
import re
import statistics
import time
import unicodedata
import wave
from datetime import datetime
from pathlib import Path

from . import ativacao, banco

log = logging.getLogger('solis.voz_teste')

TAXA = ativacao.TAXA
TOLERANCIA = 6.0     # segundos depois do fim da janela em que o texto ainda conta
PREPARO = 2.0        # o intervalo entre uma frase e outra (a tela mostra "prepare-se")
INICIO = 3.0         # silêncio no começo: a escuta aprende o ruído do ambiente
META = 0.9           # o princípio 3: 9 em 10
PARECIDO = 0.75      # o pedido entendido conta como certo a partir desta semelhança

# O roteiro: (tipo, o que a tela mostra, o pedido esperado, segundos de janela).
# Chamadas e trechos sem "Solis" intercalados, como no uso de verdade.
ROTEIRO = [
    ('chamada', 'Diga: "Solis, que horas são?"', 'que horas são', 8),
    ('chamada', 'Diga: "Solis, o que eu tenho amanhã?"', 'o que eu tenho amanhã', 8),
    ('sem', 'Diga: "O sol está forte hoje."', '', 7),
    ('chamada', 'Diga: "Solis, me lembra de beber água daqui a vinte minutos."',
     'me lembra de beber água daqui a vinte minutos', 10),
    ('chamada', 'Diga "Solis", espere um segundo, e diga: "que dia é hoje?"', 'que dia é hoje', 10),
    ('sem', 'Fale normalmente sobre o seu dia, sem dizer "Solis".', '', 20),
    ('chamada', 'Diga: "Ei Solis, quanto é quinze vezes três?"', 'quanto é quinze vezes três', 8),
    ('chamada', 'Mais baixo que o normal: "Solis, que horas são?"', 'que horas são', 8),
    ('sem', 'Diga: "A Lis vai chegar mais tarde."', '', 7),
    ('chamada', 'Diga: "Solis, anota que gastei trinta reais no almoço."',
     'anota que gastei trinta reais no almoço', 10),
    ('chamada', 'Um passo longe do microfone: "Solis, o que eu tenho hoje?"', 'o que eu tenho hoje', 9),
    ('sem', 'Diga: "Solidão, solista, sólido."', '', 7),
    ('chamada', 'Rápido: "Solis, desliga a música."', 'desliga a música', 7),
    ('chamada', 'Diga: "Solis, abre a minha agenda de sexta."', 'abre a minha agenda de sexta', 8),
    ('sem', 'Fique em silêncio.', '', 10),
    ('chamada', 'Diga: "Solis, pesquisa o preço do dólar hoje."', 'pesquisa o preço do dólar hoje', 9),
    ('sem', 'Leia em voz alta: "Amanhã cedo eu tenho reunião com a equipe de dados às nove horas."', '', 10),
    ('chamada', 'Diga: "Solis, como está o tempo lá fora?"', 'como está o tempo lá fora', 8),
]


class TesteInvalido(Exception):
    pass


def pasta() -> Path:
    return banco.pasta() / 'voz-teste'


def roteiro() -> dict:
    """O roteiro com os tempos: a tela segue isto, e a medida usa o mesmo."""
    passos, t = [], INICIO
    for i, (tipo, mostrar, esperado, segundos) in enumerate(ROTEIRO):
        t += PREPARO
        passos.append({'i': i, 'tipo': tipo, 'mostrar': mostrar, 'esperado': esperado,
                       'inicio': round(t, 2), 'fim': round(t + segundos, 2)})
        t += segundos
    return {'inicio': INICIO, 'preparo': PREPARO, 'passos': passos, 'duracao': round(t + 2.0, 2)}


# — guardar ————————————————————————————————————————————————————————————————————
def _ler_wav(dados: bytes) -> array.array:
    try:
        with wave.open(io.BytesIO(dados)) as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != TAXA:
                raise TesteInvalido('o áudio precisa ser mono, 16 bits, 16 kHz')
            amostras = array.array('h')
            amostras.frombytes(w.readframes(w.getnframes()))
            return amostras
    except (wave.Error, EOFError) as e:
        raise TesteInvalido('não é um WAV') from e


def guardar(dados: bytes, passos: list[dict] | None = None) -> dict:
    """A gravação e o roteiro que ela seguiu (os tempos de verdade de cada
    frase, como a tela mostrou)."""
    amostras = _ler_wav(dados)
    duracao = len(amostras) / TAXA
    if duracao < 10:
        raise TesteInvalido('gravação curta demais')
    id_ = datetime.now().strftime('%Y%m%d-%H%M%S')
    destino = pasta() / id_
    destino.mkdir(parents=True, exist_ok=True)
    (destino / 'gravacao.wav').write_bytes(dados)
    (destino / 'roteiro.json').write_text(json.dumps({'passos': passos or roteiro()['passos']}, ensure_ascii=False,
                                                     indent=1), encoding='utf-8')
    return {'id': id_, 'duracao': round(duracao, 1)}


def listar() -> list[dict]:
    saida = []
    if not pasta().is_dir():
        return saida
    for d in sorted(pasta().iterdir(), reverse=True):
        if not (d / 'gravacao.wav').is_file():
            continue
        medidas = {}
        for m in d.glob('medida-*.json'):
            try:
                medidas[m.stem.removeprefix('medida-')] = json.loads(m.read_text(encoding='utf-8'))['resumo']
            except (OSError, ValueError, KeyError):
                continue
        saida.append({'id': d.name, 'medidas': medidas})
    return saida


# — medir ——————————————————————————————————————————————————————————————————————
def _normal(texto: str) -> str:
    """Minúsculas, sem acento nem pontuação: "Que horas são?" → "que horas sao"."""
    sem = ''.join(c for c in unicodedata.normalize('NFD', texto.lower()) if unicodedata.category(c) != 'Mn')
    # O Whisper escreve "20", o roteiro diz "vinte": os dois viram dígito.
    return ' '.join(NUMEROS.get(p, p) for p in re.sub(r'[^a-z0-9 ]+', ' ', sem).split())


NUMEROS = {n: str(i) for i, ns in enumerate([
    ['zero'], ['um', 'uma'], ['dois', 'duas'], ['tres'], ['quatro'], ['cinco'], ['seis'], ['sete'], ['oito'], ['nove'],
    ['dez'], ['onze'], ['doze'], ['treze'], ['quatorze', 'catorze'], ['quinze'], ['dezesseis'], ['dezessete'],
    ['dezoito'], ['dezenove'], ['vinte']]) for n in ns}
NUMEROS.update({'trinta': '30', 'quarenta': '40', 'cinquenta': '50', 'sessenta': '60'})


def parecido(ouvido: str, esperado: str) -> float:
    return difflib.SequenceMatcher(None, _normal(ouvido), _normal(esperado)).ratio()


# Palavras que não carregam o pedido (o "entendeu" olha as outras).
VAZIAS = {'que', 'uma', 'umas', 'uns', 'para', 'pra', 'por', 'com', 'sem', 'dos', 'das', 'nos', 'nas', 'meu', 'minha',
          'seu', 'sua', 'lhe', 'ele', 'ela', 'isso', 'esta', 'este', 'esse', 'essa', 'aqui', 'ali', 'eu', 'voce'}
PALAVRA_CERTA = 0.8  # "dolar" e "delar" contam; "musica" e "mcp", não


def entendeu(ouvido: str, esperado: str) -> bool:
    """O pedido certo: cada palavra de conteúdo do esperado aparece no ouvido
    (com um erro de letra perdoado). Mais justo que a semelhança da frase
    inteira: "desliga a MCP" parecia 83% com "desliga a música" e passava."""
    palavras = _normal(ouvido).split()
    # Duas palavras coladas também valem: "a nota" é "anota".
    ouvidas = palavras + [a + b for a, b in zip(palavras, palavras[1:])]
    conteudo = [p for p in _normal(esperado).split()
                if (len(p) >= 3 or p.isdigit()) and p not in VAZIAS] or _normal(esperado).split()
    def tem(p):
        return any(difflib.SequenceMatcher(None, p, o).ratio() >= PALAVRA_CERTA for o in ouvidas)
    return bool(conteudo) and all(tem(p) for p in conteudo)


def _fim_da_fala(amostras: array.array, inicio: float, fim: float, ate: float | None = None) -> float | None:
    """Quando a pessoa parou de falar (Silero VAD): o fim do último pedaço de
    fala da janela que acabou até `ate` (o momento do texto). Sem o `ate`, o
    16/11/2026 deu tempos negativos: o Matheus continuou falando depois do
    pedido, e o "fim da fala" caía depois do texto."""
    import numpy as np
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    a, b = int(inicio * TAXA), int(min(len(amostras), (fim + 1.0) * TAXA))
    if b <= a:
        return None
    trecho = np.frombuffer(amostras[a:b].tobytes(), dtype=np.int16).astype(np.float32) / 32768.0
    falas = get_speech_timestamps(trecho, VadOptions(min_silence_duration_ms=500, speech_pad_ms=0))
    fins = [inicio + f['end'] / TAXA for f in falas]
    antes = [f for f in fins if ate is None or f <= ate]
    return round((antes or fins or [None])[-1], 2) if (antes or fins) else None


class WhisperFalhou(Exception):
    pass


async def _transcrever(audio: bytes) -> tuple[str, float]:
    """Áudio ruim (vazio) é "não ouviu", como ao vivo; o Whisper sem modelo ou
    caindo não: a medida inteira não vale, e diz por quê."""
    from . import voz
    t0 = time.perf_counter()
    try:
        texto = (await voz.transcrever(audio, vad=False))['texto']
    except voz.AudioRuim:
        texto = ''
    except Exception as e:
        log.exception('o Whisper falhou no teste da escuta')
        raise WhisperFalhou(f'o Whisper falhou: {type(e).__name__}: {e}'[:300]) from e
    return texto, time.perf_counter() - t0


async def rodar_escuta(amostras: array.array, transcrever=_transcrever, vad: str = 'energia') -> list[dict]:
    """A escuta de hoje sobre a gravação, como no laço do /escuta: cada evento com
    o momento da gravação em que saiu (`t`) e quando o texto ficou pronto
    (`pronto`, somando o tempo do Whisper)."""
    escuta = ativacao.Escuta(whisper=True, vad=vad)
    eventos, n = [], escuta.n
    # Até quando o Whisper está ocupado (no tempo da gravação): no /escuta o laço
    # espera a transcrição, e o áudio que chega nesse tempo fica na fila.
    livre = 0.0
    dados = amostras.tobytes()
    passo = n * 2
    for k in range(0, len(dados) - passo + 1, passo):
        t = (k + passo) / 2 / TAXA
        for tipo, audio in escuta.alimentar(dados[k:k + passo]):
            if tipo in ('previa', 'frase'):
                texto, gasto = await transcrever(audio)
                livre = max(livre, t) + gasto
                achou, resto = ativacao.palavra_no_inicio(texto)
                if not achou:
                    escuta.descartar()
                    # Guardado pra entender a chamada que não acordou: o que ele ouviu.
                    eventos.append({'tipo': 'descartado', 't': round(t, 2), 'pronto': round(livre, 2), 'ouviu': texto})
                    continue
                eventos.append({'tipo': 'ativou', 't': round(t, 2), 'pronto': round(livre, 2), 'ouviu': texto})
                pronto = escuta.confirmar(resto=resto if tipo == 'frase' else '')
                if pronto:
                    eventos.append({'tipo': 'texto', 't': round(t, 2), 'pronto': round(livre, 2), 'texto': pronto})
            elif tipo == 'rascunho':
                texto, gasto = await transcrever(audio)
                livre = max(livre, t) + gasto
                escuta.guardar_rascunho(ativacao.palavra_no_inicio(texto)[1])
            elif tipo == 'comando':
                if audio is None:
                    eventos.append({'tipo': 'nada', 't': round(t, 2), 'pronto': round(max(livre, t), 2)})
                    continue
                resto = escuta.pronto
                if resto is None:
                    texto, gasto = await transcrever(audio)
                    livre = max(livre, t) + gasto
                    _, resto = ativacao.palavra_no_inicio(texto)
                eventos.append({'tipo': 'texto' if resto else 'nada', 't': round(t, 2), 'pronto': round(max(livre, t), 2),
                                'texto': resto})
    return eventos


def pontuar(passos: list[dict], eventos: list[dict], amostras: array.array) -> dict:
    """Cada passo do roteiro contra o que a escuta fez nele."""
    resultado = []
    for k, p in enumerate(passos):
        # Cada evento é de um passo só: do começo dele até o começo do próximo (a
        # chamada que demora ainda conta, sem invadir o trecho seguinte).
        ate = passos[k + 1]['inicio'] if k + 1 < len(passos) else p['fim'] + TOLERANCIA
        dentro = [e for e in eventos if p['inicio'] <= e['t'] < ate]
        ativou = any(e['tipo'] == 'ativou' for e in dentro)
        if p['tipo'] == 'chamada':
            texto = next((e for e in dentro if e['tipo'] == 'texto'), None)
            # Desde o "Prepare-se": tem quem comece a falar antes da hora (16/11/2026).
            fim_fala = _fim_da_fala(amostras, max(0.0, p['inicio'] - PREPARO), p['fim'], texto['t'] if texto else None)
            semelhanca = parecido(texto['texto'], p['esperado']) if texto else 0.0
            resultado.append({
                **p, 'acordou': ativou or bool(texto), 'ouvido': texto['texto'] if texto else '',
                'semelhanca': round(semelhanca, 2), 'entendeu': bool(texto) and entendeu(texto['texto'], p['esperado']),
                'fim_fala': fim_fala,
                'latencia': round(texto['pronto'] - fim_fala, 2) if texto and fim_fala is not None else None,
                'descartados': [e['ouviu'] for e in dentro if e['tipo'] == 'descartado']})
        else:
            resultado.append({**p, 'falsos': sum(1 for e in dentro if e['tipo'] == 'ativou'),
                              'ouviu': [e.get('ouviu', '') for e in dentro if e['tipo'] == 'ativou']})
    chamadas = [r for r in resultado if r['tipo'] == 'chamada']
    sem = [r for r in resultado if r['tipo'] == 'sem']
    latencias = [r['latencia'] for r in chamadas if r['latencia'] is not None]
    acordou = sum(r['acordou'] for r in chamadas)
    certos = sum(r['entendeu'] for r in chamadas)
    return {
        'resumo': {
            'chamadas': len(chamadas), 'acordou': acordou, 'entendeu': certos,
            'falsos': sum(r['falsos'] for r in sem), 'trechos_sem': len(sem),
            'latencia_mediana': round(statistics.median(latencias), 2) if latencias else None,
            'latencia_max': max(latencias) if latencias else None,
            'passou': bool(chamadas) and certos / len(chamadas) >= META and not sum(r['falsos'] for r in sem),
        },
        'passos': resultado,
    }


async def medir(id_: str, motor: str = 'atual', transcrever=_transcrever) -> dict:
    """Roda a escuta numa gravação guardada e guarda a medida (medida-<motor>.json)."""
    d = pasta() / id_
    if not re.match(r'^[0-9-]+$', id_) or not (d / 'gravacao.wav').is_file():
        raise TesteInvalido('gravação não encontrada')
    amostras = _ler_wav((d / 'gravacao.wav').read_bytes())
    passos = json.loads((d / 'roteiro.json').read_text(encoding='utf-8'))['passos']
    t0 = time.perf_counter()
    try:
        # O motor diz o que medir: 'atual' (a escuta como está no Solis) ou 'energia'/'silero'.
        eventos = await rodar_escuta(amostras, transcrever, ativacao.VAD if motor == 'atual' else motor)
    except WhisperFalhou as e:
        r = {'resumo': {'motor': motor, 'erro': str(e), 'medido': datetime.now().isoformat(timespec='seconds')}}
        (d / f'medida-{motor}.json').write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding='utf-8')
        return r
    r = await asyncio.to_thread(pontuar, passos, eventos, amostras)
    r['resumo'].update(motor=motor, medido=datetime.now().isoformat(timespec='seconds'),
                       segundos=round(time.perf_counter() - t0, 1))
    r['eventos'] = eventos
    (d / f'medida-{motor}.json').write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding='utf-8')
    log.info('teste da escuta %s (%s): %s', id_, motor, r['resumo'])
    return r
