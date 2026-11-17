"""O teste do modo Conversa (voz em tempo real, IDEIAS.md): perguntas faladas em portugues por uma
voz sintetica (a Maria do Windows, gerada aqui, nada do Matheus) vao pro Gemini Live como um
microfone ao vivo (100 ms por vez, depois silencio). Mede: do fim da fala ao primeiro som da
resposta, o que ele ouviu, o que respondeu, se acertou, e os tokens. Guarda o audio de cada resposta.

Uso (na pasta backend): .venv/Scripts/python ../design/testar-conversa.py <modelo> [<modelo> ...]
Medido em 16/11/2026: ver docs/ESCOPO.md (o modo Conversa) e as amostras em design/conversa-amostras/.
ATENCAO: o WAV da Maria do Windows termina com ~0,87 s de silencio; a latencia impressa conta do fim
do ARQUIVO - some esse silencio pra ter a latencia do fim da fala de verdade.
A chave e a do Gemini guardada no Solis (cofre do Windows): lida aqui, nunca impressa."""
import asyncio
import json
import subprocess
import sys
import time
import unicodedata
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))
from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

from solis import apis  # noqa: E402

# Fora do repositorio: as respostas em audio e o resultado (o repositorio guarda so as amostras escolhidas).
AQUI = Path(__import__('tempfile').gettempdir()) / 'solis-conversa-teste'
AQUI.mkdir(exist_ok=True)
SISTEMA = ('Você é o Solis, o assistente pessoal do Matheus, numa conversa por voz. Responda sempre em português '
           'do Brasil, em uma ou duas frases curtas, como alguém falando em voz alta. Quando não souber, diga que '
           'não sabe.')
PERGUNTAS = [
    ('Qual a capital da Austrália?', [['canberra']]),
    ('Quanto é dezessete vezes oito?', [['136', 'cento e trinta e seis']]),
    ('Quem escreveu Dom Casmurro?', [['machado']]),
    ('Qual o maior oceano da Terra?', [['pacifico']]),
    ('Em que ano o homem pisou na Lua pela primeira vez?', [['1969', 'sessenta e nove']]),
    ('Quantos planetas tem o sistema solar?', [['oito', '8']]),
    ('Qual o elemento químico de símbolo Fe?', [['ferro']]),
    ('Quanto é a raiz quadrada de cento e quarenta e quatro?', [['12', 'doze']]),
    ('Me dá uma dica rápida pra dormir melhor.', None),
    ('Me conta uma curiosidade sobre o Sol, em uma frase.', None),
]
TAXA_ENTRA, TAXA_SAI = 16000, 24000
PEDACO = TAXA_ENTRA * 2 // 10  # 100 ms de PCM 16 bits


def sem_acento(t):
    return ''.join(c for c in unicodedata.normalize('NFD', t.lower()) if unicodedata.category(c) != 'Mn')


def falar(texto: str, destino: Path) -> bytes:
    """A pergunta na voz Maria do Windows, 16 kHz mono 16 bits."""
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
        return w.readframes(w.getnframes())


async def uma(cliente, modelo: str, pcm: bytes) -> dict:
    cfg = types.LiveConnectConfig(
        response_modalities=['AUDIO'],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction=SISTEMA,
    )
    r = {'ouviu': '', 'disse': '', 'latencia': None, 'erro': None, 'uso': None}
    saida = bytearray()
    async with cliente.aio.live.connect(model=modelo, config=cfg) as s:
        fim_fala = {}

        async def enviar():
            for i in range(0, len(pcm), PEDACO):
                await s.send_realtime_input(audio=types.Blob(data=pcm[i:i + PEDACO], mime_type='audio/pcm;rate=16000'))
                await asyncio.sleep(0.1)
            fim_fala['t'] = time.perf_counter()
            silencio = b'\0' * PEDACO
            for _ in range(60):  # ate 6 s de silencio: quem decide que a fala acabou e o VAD dele
                await s.send_realtime_input(audio=types.Blob(data=silencio, mime_type='audio/pcm;rate=16000'))
                await asyncio.sleep(0.1)

        envio = asyncio.create_task(enviar())
        primeiro = None
        try:
            async for msg in s.receive():
                if msg.usage_metadata:
                    u = msg.usage_metadata
                    r['uso'] = {'entrada': u.prompt_token_count, 'saida': u.response_token_count,
                                'total': u.total_token_count, 'pensando': u.thoughts_token_count}
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
                if sc.turn_complete:
                    break
        finally:
            envio.cancel()
    if primeiro and 't' in fim_fala:
        r['latencia'] = round(primeiro - fim_fala['t'], 2)
    r['segundos_de_resposta'] = round(len(saida) / 2 / TAXA_SAI, 1)
    r['_audio'] = bytes(saida)
    return r


async def main(modelos):
    # v1beta explicito: sem ele, o padrao desta versao do SDK nao atende a Live API (HTTP 404, medido).
    cliente = genai.Client(api_key=apis._chave_de('gemini'), http_options=types.HttpOptions(api_version='v1beta'))
    todos = {}
    for modelo in modelos:
        linhas = []
        for i, (pergunta, grupos) in enumerate(PERGUNTAS):
            pcm = falar(pergunta, AQUI / f'pergunta-{i:02}.wav')
            try:
                r = await asyncio.wait_for(uma(cliente, modelo, pcm), timeout=45)
            except Exception as e:  # noqa: BLE001 — a pergunta falha, o teste segue
                r = {'ouviu': '', 'disse': '', 'latencia': None, 'erro': f'{type(e).__name__}: {e}'[:300], 'uso': None,
                     '_audio': b''}
            audio = r.pop('_audio', b'')
            if audio:
                with wave.open(str(AQUI / f'{modelo}-{i:02}.wav'), 'wb') as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(TAXA_SAI)
                    w.writeframes(audio)
            r['pergunta'] = pergunta
            r['certo'] = None if grupos is None else all(any(sem_acento(p) in sem_acento(r['disse']) for p in g) for g in grupos)
            linhas.append(r)
            print(f"[{modelo}] {r['latencia']} s  certo={r['certo']}  ouviu={r['ouviu'][:50]!r}  disse={r['disse'][:90]!r}"
                  + (f"  ERRO {r['erro']}" if r.get('erro') else ''), flush=True)
            await asyncio.sleep(2)
        todos[modelo] = linhas
        lat = sorted(x['latencia'] for x in linhas if x['latencia'] is not None)
        certos = [x['certo'] for x in linhas if x['certo'] is not None]
        print(f"[{modelo}] RESUMO: respondeu {len(lat)}/{len(linhas)}, certas {sum(certos)}/{len(certos)}, "
              f"latencia mediana {lat[len(lat) // 2] if lat else '-'} s (de {lat[0] if lat else '-'} a {lat[-1] if lat else '-'})",
              flush=True)
    (AQUI / 'resultado.json').write_text(json.dumps(todos, ensure_ascii=False, indent=1), encoding='utf-8')
    print('FIM', flush=True)


asyncio.run(main(sys.argv[1:] or ['gemini-3.8-live']))
