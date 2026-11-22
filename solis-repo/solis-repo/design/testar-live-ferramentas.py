"""O comparativo de tempo real (22/11/2026): o Gemini Live fala pra fala COM as
ferramentas do Solis (cotação, clima, jogos, datas, lembrete, agenda, a busca), o
modo Pedido sem o caminho escuta → texto → cérebro → voz.

As perguntas são faladas por uma voz sintética (a Maria do Windows, nada do
Matheus), mandadas como um microfone ao vivo (100 ms por vez), sem o silêncio do
fim do arquivo: o tempo conta do FIM DA FALA de verdade até o primeiro som. As
ferramentas rodam pelo corpo do Solis (corpo.Corpo), numa cópia do banco; os
cartões de aprovação são recusados (nada roda no PC).

Uso (na pasta backend): .venv/Scripts/python ../design/testar-live-ferramentas.py [modelo ...]
Variáveis: SILENCIO_MS (o silêncio que o Gemini espera pra decidir que a fala
acabou; sem ela, o padrão dele), SO (só as perguntas que casam)."""
import asyncio
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))
copia = Path(tempfile.mkdtemp()) / 'solis.db'
_o = sqlite3.connect(f"file:{Path(os.environ['APPDATA']) / 'Solis' / 'solis.db'}?mode=ro", uri=True)
_d = sqlite3.connect(copia)
_o.backup(_d)
_o.close()
_d.close()
from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

from solis import agente, apis, banco, corpo, navegador, ollama, tela  # noqa: E402

banco.usar(copia)
navegador.escolhido = lambda: None
tela.ligada = lambda: False

AQUI = Path(tempfile.gettempdir()) / 'solis-live-ferramentas'
AQUI.mkdir(exist_ok=True)
TAXA_ENTRA, TAXA_SAI = 16000, 24000
PEDACO = TAXA_ENTRA * 2 // 10  # 100 ms

SISTEMA = (
    'Você é o Solis, o assistente pessoal do Matheus, falando com ele por voz em tempo real. Fale em português '
    'do Brasil, direto ao ponto, em uma a três frases curtas, como um assistente competente falando em voz alta. '
    'Números em algarismos. O que você já sabe (fatos, geografia, contas), responda direto, sem ferramenta. '
    'Use as ferramentas do Solis: cotação, clima, jogos de um time e conta com datas pelas '
    'ferramentas próprias; outra informação de hoje, busque com WebFetch num endereço de busca '
    '(https://www.google.com/search?q=...). Lembrete e agenda pelas ferramentas. Nunca diga que fez algo que a '
    'ferramenta não fez. A data e a hora de agora: {agora}.'
)
# (pergunta, regex que a resposta falada tem que ter, ferramentas aceitas (None: tanto faz))
PERGUNTAS = [
    ('Qual é a cotação do dólar hoje?', r'5[,.]\d|cinco', {'mcp__solis__cotacao'}),
    ('Vai chover hoje em Ribeirão Preto?', r'chuva|chover|%|por cento|graus', {'mcp__solis__clima'}),
    ('Quem ganhou o último jogo do Flamengo?', r'1\s*(a|x)\s*1|um a um|empat', {'mcp__solis__jogos'}),
    ('Quantos dias faltam pro Natal?', r'\b33\b|trinta e tr[eê]s', None),
    ('Me lembra de ligar pro João amanhã às dez da manhã.', r'Jo[aã]o', {'mcp__solis__criar_lembrete'}),
    ('Qual é a capital da Austrália?', r'[Cc]a[mn]berra', set()),
    ('Quanto é dezessete por cento de trezentos e quarenta?', r'57[,.]8|cinquenta e sete', set()),
    ('Pesquisa pra mim o preço de um PlayStation 5 no Brasil.', r'R\$|reais|mil', {'WebFetch'}),
]


def sem_acento(t):
    return ''.join(c for c in unicodedata.normalize('NFD', t.lower()) if unicodedata.category(c) != 'Mn')


def falar(texto: str, destino: Path) -> bytes:
    """A pergunta na voz Maria do Windows, 16 kHz, sem o silêncio do fim."""
    if not destino.exists():
        script = (
            'Add-Type -AssemblyName System.Speech; '
            '$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
            "$s.SelectVoice('Microsoft Maria Desktop'); "
            '$f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, '
            '[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono); '
            f"$s.SetOutputToWaveFile('{destino}', $f); $s.Speak([Console]::In.ReadToEnd()); $s.Dispose()")
        subprocess.run(['powershell', '-NoProfile', '-Command', script], input=texto, text=True, encoding='utf-8',
                       check=True)
    with wave.open(str(destino)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    energia = np.abs(x.astype(np.int32))
    fala = np.where(energia > 300)[0]
    fim = int(fala[-1]) + 1 if len(fala) else len(x)
    return x[:fim].tobytes()


class Etapas:
    def __init__(self):
        self.lista = []

    def marcar(self, etapa, **dados):
        self.lista.append((etapa, dados))
        if etapa == 'aprovacao':
            asyncio.get_running_loop().call_later(0.05, agente.responder_aprovacao, dados['id'], False)


def ferramentas_do_solis(c: corpo.Corpo, specs: list[dict]) -> list:
    return [types.Tool(function_declarations=[types.FunctionDeclaration(
        name=s['function']['name'], description=s['function']['description'],
        parameters_json_schema=s['function']['parameters']) for s in specs])]


async def uma(cliente, modelo: str, pcm: bytes) -> dict:
    etapas = Etapas()
    c = corpo.Corpo(banco.nova_conversa(), etapas, navegar=False, cerebro='gemini-live')
    c.voz = True
    specs = await c.especificacoes()
    agora = time.strftime('%A, %d/%m/%Y, %H:%M')
    vad = None
    if os.environ.get('SILENCIO_MS'):
        vad = types.RealtimeInputConfig(automatic_activity_detection=types.AutomaticActivityDetection(
            silence_duration_ms=int(os.environ['SILENCIO_MS'])))
    cfg = types.LiveConnectConfig(
        response_modalities=['AUDIO'],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=SISTEMA.format(agora=agora),
        tools=ferramentas_do_solis(c, specs),
        **({'realtime_input_config': vad} if vad else {}),
    )
    r = {'ouviu': '', 'disse': '', 'latencia': None, 'ferramentas': [], 'tempo_ferramentas': 0.0, 'erro': None}
    saida = bytearray()
    async with cliente.aio.live.connect(model=modelo, config=cfg) as s:
        fim_fala = {}

        async def enviar():
            for i in range(0, len(pcm), PEDACO):
                await s.send_realtime_input(audio=types.Blob(data=pcm[i:i + PEDACO], mime_type='audio/pcm;rate=16000'))
                await asyncio.sleep(0.1)
            fim_fala['t'] = time.perf_counter()
            silencio = b'\0' * PEDACO
            for _ in range(200):  # o silêncio da sala: quem decide que a fala acabou é o VAD dele
                await s.send_realtime_input(audio=types.Blob(data=silencio, mime_type='audio/pcm;rate=16000'))
                await asyncio.sleep(0.1)

        envio = asyncio.create_task(enviar())
        primeiro = None
        acabou = False
        try:
            # O receive() do SDK entrega uma rodada (até o turn_complete): depois da
            # ferramenta, a resposta falada vem na rodada seguinte.
            while not acabou:
                async for msg in s.receive():
                    if msg.tool_call:
                        respostas = []
                        for fc in msg.tool_call.function_calls or []:
                            t0 = time.perf_counter()
                            resultado = await c.rodar(fc.name, dict(fc.args or {}))
                            r['tempo_ferramentas'] += time.perf_counter() - t0
                            r['ferramentas'].append(fc.name)
                            respostas.append(types.FunctionResponse(id=fc.id, name=fc.name,
                                                                    response={'resultado': resultado}))
                        await s.send_tool_response(function_responses=respostas)
                        continue
                    sc = msg.server_content
                    if not sc:
                        continue
                    if sc.input_transcription and sc.input_transcription.text:
                        r['ouviu'] += sc.input_transcription.text
                    if sc.output_transcription and sc.output_transcription.text:
                        r['disse'] += sc.output_transcription.text
                    if sc.model_turn:
                        for parte in sc.model_turn.parts or []:
                            if parte.inline_data and parte.inline_data.data:
                                if primeiro is None:
                                    primeiro = time.perf_counter()
                                saida += parte.inline_data.data
                    if sc.turn_complete and primeiro is not None:
                        acabou = True
        finally:
            envio.cancel()
    if primeiro and 't' in fim_fala:
        r['latencia'] = round(primeiro - fim_fala['t'], 2)
    r['tempo_ferramentas'] = round(r['tempo_ferramentas'], 2)
    r['_audio'] = bytes(saida)
    return r


async def main(modelos):
    cliente = genai.Client(api_key=apis._chave_de('gemini'), http_options=types.HttpOptions(api_version='v1beta'))
    perguntas = [p for p in PERGUNTAS if not os.environ.get('SO') or re.search(os.environ['SO'], p[0])]
    todos = {}
    for modelo in modelos:
        linhas = []
        for i, (pergunta, padrao, aceitas) in enumerate(perguntas):
            # O áudio pelo texto da pergunta, não pela posição (com SO, a posição muda).
            import hashlib
            pcm = falar(pergunta, AQUI / f'pergunta-{hashlib.sha1(pergunta.encode()).hexdigest()[:10]}.wav')
            try:
                r = await asyncio.wait_for(uma(cliente, modelo, pcm), timeout=60)
            except Exception as e:  # noqa: BLE001 — a pergunta falha, o teste segue
                r = {'ouviu': '', 'disse': '', 'latencia': None, 'ferramentas': [], 'erro': f'{type(e).__name__}: {e}'[:300],
                     '_audio': b''}
            audio = r.pop('_audio', b'')
            if audio:
                with wave.open(str(AQUI / f'{modelo}-{i:02}.wav'), 'wb') as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(TAXA_SAI)
                    w.writeframes(audio)
            r['pergunta'] = pergunta
            texto = sem_acento(r['disse'])
            ok_texto = bool(re.search(sem_acento(padrao), texto)) if r['disse'] else False
            ok_ferr = aceitas is None or (bool(set(r['ferramentas']) & aceitas) if aceitas else not r['ferramentas'])
            r['certo'] = ok_texto and ok_ferr and not r['erro']
            linhas.append(r)
            print(json.dumps({k: r[k] for k in ('pergunta', 'certo', 'latencia', 'ferramentas', 'tempo_ferramentas',
                                                'disse', 'erro') if k in r}, ensure_ascii=False), flush=True)
            await asyncio.sleep(3)
        todos[modelo] = linhas
        lat = sorted(x['latencia'] for x in linhas if x['latencia'] is not None)
        print(f"RESUMO [{modelo}] certas {sum(x['certo'] for x in linhas)}/{len(linhas)}, respondeu {len(lat)}, "
              f"primeiro som: mediana {lat[len(lat) // 2] if lat else '-'} s (de {lat[0] if lat else '-'} a "
              f"{lat[-1] if lat else '-'})", flush=True)
    (AQUI / 'resultado.json').write_text(json.dumps(todos, ensure_ascii=False, indent=1), encoding='utf-8')


asyncio.run(main(sys.argv[1:] or ['gemini-3.8-live']))
