"""O modo Conversa (IDEIAS.md → Voz): bate-papo por voz em tempo real, pelo Gemini
Live, com interrupção no meio e sem o caminho do modo Pedido (escuta → texto →
cérebro → voz). Acabou (30 s sem ninguém falar), volta pro modo Pedido.

Decisões do Matheus (16–17/11/2026): Gemini Live na faixa grátis (o Google pode
usar o que é mandado pra melhorar os produtos dele; a paga, ~US$ 0,003 por
pergunta, fica pra avaliar); entrar falando ("Solis, vamos conversar") ou por um
botão; o que for dito fica salvo na conversa. Medido no teste (design/
testar-conversa.py, 16/11/2026): gemini-3.8-live acertou 8 de 8 e deu o primeiro
som 1,37 s depois do fim da fala (mediana).

A ponte: a tela manda o microfone (PCM 16 bits, 16 kHz, mono) em pedaços; o
Gemini decide quando a pessoa parou (o VAD dele) e devolve a voz (PCM 16 bits,
24 kHz) aos pedaços, que vão direto pra tela; as transcrições das duas falas
viram as mensagens da conversa. O que é privado (memórias, mensagens) não vai
no contexto. Nesta conversa o Gemini não age: não tem ferramentas."""
import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable

from . import banco, memoria, ollama

log = logging.getLogger('solis.conversa_voz')

MODELO = os.environ.get('SOLIS_CONVERSA_MODELO', 'gemini-3.8-live')
# Sem ninguém falar por isso, a conversa acaba (IDEIAS.md: "desliga sozinho após ~30 s de silêncio").
SILENCIO_FIM_S = 30.0
HISTORICO = 12  # as últimas mensagens da conversa que vão de contexto

SISTEMA = (
    'Você é o Solis, o assistente pessoal do Matheus, numa conversa por voz em tempo real. Fale em '
    'português do Brasil, como numa conversa de verdade: frases curtas e naturais, sem listas e sem '
    'enrolar. Ele pode te interromper a qualquer momento. Nesta conversa você só conversa: não age no '
    'computador, não abre programas, não pesquisa na internet e não anota nada. Se ele pedir uma ação, '
    'diga que pra isso é melhor ele pedir com "Solis" fora do modo conversa. Nunca diga que fez algo '
    'que não fez. Quando não souber, diga que não sabe.'
)


def sistema(conversa: int | None) -> str:
    """O que o Gemini sabe: quem ele é, o que o Solis sabe do Matheus (só o que
    não é privado) e o fim da conversa aberta (só o que não é privado)."""
    memorias = [m for m in banco.memorias() if not m.get('privada')]
    partes = [SISTEMA, ollama.contexto(memorias)]
    if conversa is not None:
        msgs = [m for m in banco.mensagens(conversa) if not m.get('privada')][-HISTORICO:]
        if msgs:
            partes.append('A conversa até agora:\n' + '\n'.join(
                f'{"Matheus" if m["papel"] == "pessoa" else "Solis"}: {m["texto"]}' for m in msgs))
    return '\n\n'.join(p for p in partes if p)


def configuracao(conversa: int | None, voz: str):
    from google.genai import types
    return types.LiveConnectConfig(
        response_modalities=['AUDIO'],
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voz))),
        system_instruction=sistema(conversa),
    )


def abrir(conversa: int | None, voz: str):
    """A sessão do Gemini Live (um gerenciador de contexto). v1beta explícito: o
    padrão do SDK 3.4.0 não atende a Live API (HTTP 404, medido em 16/11/2026)."""
    from google import genai
    from google.genai import types

    from . import apis
    chave = apis._chave_de('gemini')
    if not chave:
        raise SemChave('falta a chave do Gemini (Configurações → Cérebros)')
    cliente = genai.Client(api_key=chave, http_options=types.HttpOptions(api_version='v1beta'))
    return cliente.aio.live.connect(model=MODELO, config=configuracao(conversa, voz))


class SemChave(Exception):
    pass


async def conduzir(
    sessao,
    receber: Callable[[], Awaitable[dict]],
    mandar_audio: Callable[[bytes], Awaitable[None]],
    mandar: Callable[[dict], Awaitable[None]],
    ao_turno: Callable[[str, str], Awaitable[None]],
    relogio: Callable[[], float] = time.monotonic,
    silencio_fim: float | None = None,
) -> str:
    """Leva a conversa até ela acabar; devolve o porquê ('silencio', 'fim' — a
    tela pediu —, 'saiu' — a tela fechou — ou 'erro').

    `receber()`: o próximo da tela, {'audio': bytes} ou {'fim': True} ou
    {'saiu': True}. `ao_turno(fala, resposta)`: uma troca completa (pra salvar)."""
    from google.genai import types
    limite = SILENCIO_FIM_S if silencio_fim is None else silencio_fim
    ultimo = {'t': relogio()}
    motivo = {'v': ''}

    async def subir():
        while True:
            m = await receber()
            if m.get('saiu') or m.get('fim'):
                motivo['v'] = 'saiu' if m.get('saiu') else 'fim'
                return
            if m.get('audio'):
                await sessao.send_realtime_input(audio=types.Blob(data=m['audio'], mime_type='audio/pcm;rate=16000'))

    async def descer():
        fala, resposta = '', ''
        while True:
            async for msg in sessao.receive():
                sc = msg.server_content
                if not sc:
                    continue
                if sc.input_transcription and sc.input_transcription.text:
                    fala += sc.input_transcription.text
                    ultimo['t'] = relogio()
                    await mandar({'tipo': 'ouviu', 'texto': fala.strip()})
                if sc.output_transcription and sc.output_transcription.text:
                    resposta += sc.output_transcription.text
                    await mandar({'tipo': 'disse', 'texto': resposta.strip()})
                if sc.model_turn:
                    for parte in sc.model_turn.parts or []:
                        if parte.inline_data and parte.inline_data.data:
                            ultimo['t'] = relogio()
                            await mandar_audio(parte.inline_data.data)
                if sc.interrupted:
                    # Ele falou por cima: a tela para de tocar na hora.
                    await mandar({'tipo': 'interrompido'})
                if sc.turn_complete:
                    if fala.strip() or resposta.strip():
                        await ao_turno(fala.strip(), resposta.strip())
                    await mandar({'tipo': 'turno', 'fala': fala.strip(), 'resposta': resposta.strip()})
                    fala, resposta = '', ''
                    ultimo['t'] = relogio()

    async def vigiar():
        while relogio() - ultimo['t'] < limite:
            await asyncio.sleep(0.5)
        motivo['v'] = 'silencio'

    tarefas = [asyncio.ensure_future(t) for t in (subir(), descer(), vigiar())]
    try:
        feitas, _ = await asyncio.wait(tarefas, return_when=asyncio.FIRST_COMPLETED)
        for t in feitas:
            if t.exception() is not None:
                log.warning('a conversa por voz caiu: %r', t.exception())
                motivo['v'] = motivo['v'] or 'erro'
    finally:
        for t in tarefas:
            t.cancel()
        await asyncio.gather(*tarefas, return_exceptions=True)
    return motivo['v'] or 'erro'


def salvar_turno(conversa: int, fala: str, resposta: str) -> tuple[int | None, int | None]:
    """A troca vira mensagens na conversa, como no modo Pedido (decisão do Matheus)."""
    ids = (None, None)
    if fala:
        ids = (banco.adicionar(conversa, 'pessoa', fala, privada=memoria.eh_privado(fala)), None)
    if resposta:
        ids = (ids[0], banco.adicionar(conversa, 'solis', resposta, cerebro='gemini-live'))
    return ids
