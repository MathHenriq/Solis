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
no contexto. Nesta conversa o Gemini não age: não tem ferramentas.

Sem o Gemini (sem a chave, a faixa grátis acabou, a conexão caiu), a conversa
segue pela reserva da Groq (conduzir_reserva, no fim deste arquivo)."""
import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable

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


def salvar_turno(conversa: int, fala: str, resposta: str, cerebro: str = 'gemini-live') -> tuple[int | None, int | None]:
    """A troca vira mensagens na conversa, como no modo Pedido (decisão do Matheus).
    `cerebro`: quem respondeu ('gemini-live', ou 'groq'/'local' pela reserva)."""
    ids = (None, None)
    if fala:
        ids = (banco.adicionar(conversa, 'pessoa', fala, privada=memoria.eh_privado(fala)), None)
    if resposta:
        ids = (ids[0], banco.adicionar(conversa, 'solis', resposta, cerebro=cerebro))
    return ids


# — A reserva: o caminho da Groq quando o Gemini Live não abre ou cai ————————————
#
# Decisão do Matheus (17/11/2026): a faixa grátis do Gemini acaba um dia, e o
# modo Conversa não pode parar com ela. Online primeiro: a reserva também é de
# nuvem — o ouvido da escuta (ativacao.Escuta) acha o fim da fala, o Whisper da
# Groq transcreve (transcricao.escuta, que guarda o privado no PC), o modelo da
# Groq responde e a voz de sempre fala (fala.falar). Mais lenta que o Gemini e
# sem interromper no meio: enquanto ele fala, o microfone não conta (sem isso,
# a voz dele nas caixas viraria a próxima fala). O privado é respondido pelo
# modelo daqui, nunca pela nuvem.

GEMINI_DESCANSO_S = 10 * 60  # o Gemini falhou: a próxima conversa já vai pela reserva
SOBRA_DA_FALA_S = 0.4  # depois do fim da voz dele, antes de voltar a ouvir (o eco da sala)
# O começo do microfone só ensina o ruído da sala (ativacao.Escuta.aprender_piso).
# PROVISÓRIO: medir com a voz do Matheus no modo Conversa.
APRENDER_PISO_S = 0.6
TAXA_SAIDA = 24000  # a tela toca PCM 16 bits a 24 kHz (o mesmo do Gemini)
FRASE_PRIVADO = ('Isso é privado, e aqui no computador não consegui responder agora. '
                 'Pergunte com "Solis" fora do modo conversa.')
FRASE_FALHOU = 'Não consegui responder agora. Pode repetir?'

_gemini_fora = {'ate': 0.0}


def gemini_descansando() -> bool:
    return time.monotonic() < _gemini_fora['ate']


def deixar_gemini(motivo: str) -> None:
    _gemini_fora['ate'] = time.monotonic() + GEMINI_DESCANSO_S
    log.info('modo conversa: o Gemini fica de lado por %d min (%s)', GEMINI_DESCANSO_S // 60, motivo[:160])


def reserva_disponivel() -> bool:
    from . import cerebros
    return cerebros.disponivel('groq')


def pcm24(audio: bytes) -> bytes:
    """O áudio da voz (mp3 ou wav) como a tela toca: PCM 16 bits, mono, 24 kHz."""
    import io

    import av
    saida = bytearray()
    with av.open(io.BytesIO(audio)) as recipiente:
        conversor = av.AudioResampler(format='s16', layout='mono', rate=TAXA_SAIDA)
        for quadro in recipiente.decode(audio=0):
            for q in conversor.resample(quadro):
                saida += q.to_ndarray().tobytes()
        for q in conversor.resample(None):
            saida += q.to_ndarray().tobytes()
    return bytes(saida)


async def _responder_nuvem(conversa: int | None, texto: str) -> str:
    from . import apis
    pedacos = [p async for p in apis.responder('groq', sistema(conversa), texto, rapido=True)]
    return ''.join(pedacos).strip()


class Mp3EmPcm:
    """O mp3 que chega aos pedaços (a Fish manda enquanto gera) virando, também
    aos pedaços, o PCM que a tela toca: o primeiro som sai com o primeiro
    pedaço, e não com o áudio inteiro. No teste de 18/11/2026 a voz inteira
    levou 3,0 s; aos pedaços, a Fish entrega o primeiro em 0,7–0,8 s."""

    def __init__(self):
        import av
        self._av = av
        self.codec = av.CodecContext.create('mp3', 'r')
        self.conversor = av.AudioResampler(format='s16', layout='mono', rate=TAXA_SAIDA)

    def _quadros(self, pacote):
        try:
            return self.codec.decode(pacote)
        except self._av.error.InvalidDataError:
            return []  # o cabeçalho (ID3/Xing) que vem antes do som

    def _pcm(self, quadros) -> bytearray:
        saida = bytearray()
        for q in quadros:
            for r in self.conversor.resample(q):
                saida += r.to_ndarray().tobytes()
        return saida

    def __call__(self, dados: bytes) -> bytes:
        saida = bytearray()
        for pacote in self.codec.parse(dados):
            saida += self._pcm(self._quadros(pacote))
        return bytes(saida)

    def fim(self) -> bytes:
        saida = bytearray()
        for pacote in self.codec.parse(None):
            saida += self._pcm(self._quadros(pacote))
        saida += self._pcm(self._quadros(None))
        for r in self.conversor.resample(None):
            saida += r.to_ndarray().tobytes()
        return bytes(saida)


async def _falar(texto: str, conversa: int | None) -> AsyncIterator[bytes]:
    """A voz de sempre (fala.falar_aos_pedacos: o privado só pela local), em PCM pra tela."""
    from . import fala
    pedacos, tipo, _ = await fala.falar_aos_pedacos(texto, conversa)
    if tipo == 'audio/mpeg':
        mp3 = Mp3EmPcm()
        async for p in pedacos:
            pcm = mp3(p)
            if pcm:
                yield pcm
        resto = mp3.fim()
        if resto:
            yield resto
        return
    yield await asyncio.to_thread(pcm24, b''.join([p async for p in pedacos]))


async def conduzir_reserva(
    conversa: int | None,
    receber: Callable[[], Awaitable[dict]],
    mandar_audio: Callable[[bytes], Awaitable[None]],
    mandar: Callable[[dict], Awaitable[None]],
    ao_turno: Callable[..., Awaitable[None]],
    local: Callable[[str, str], Awaitable[str]] | None = None,
    relogio: Callable[[], float] = time.monotonic,
    silencio_fim: float | None = None,
    ouvido=None,
    transcrever: Callable[[str, bytes], Awaitable[str]] | None = None,
    responder: Callable[[int | None, str], Awaitable[str]] | None = None,
    falar: Callable[[str, int | None], AsyncIterator[bytes]] | None = None,
) -> str:
    """Como conduzir(), pela reserva. Devolve 'silencio', 'fim' ou 'saiu'.

    `local(instrução, texto)`: a resposta do modelo daqui (o privado). Os
    últimos argumentos trocam as peças nos testes."""
    from . import ativacao, fala, transcricao
    limite = SILENCIO_FIM_S if silencio_fim is None else silencio_fim
    ouvido = ouvido or ativacao.Escuta(whisper=True)
    transcrever = transcrever or transcricao.escuta
    responder = responder or _responder_nuvem
    falar = falar or _falar
    fila: asyncio.Queue = asyncio.Queue()

    async def ler():
        while True:
            m = await receber()
            await fila.put(m)
            if m.get('saiu') or m.get('fim'):
                return

    async def proximo(ate: float) -> dict | None:
        """O próximo da tela até o relógio chegar em `ate` ({} se nada veio
        ainda; None quando o prazo passou)."""
        # O prazo primeiro: o microfone não para de mandar, e a fila nunca fica vazia.
        if relogio() >= ate:
            return None
        if not fila.empty():
            return fila.get_nowait()
        try:
            return await asyncio.wait_for(fila.get(), max(0.01, min(ate - relogio(), 0.5)))
        except TimeoutError:
            return {}

    async def esperar_tocar(ate: float) -> str | None:
        """A voz dele tocando: o microfone não conta (some da fila), só o sair."""
        while True:
            m = await proximo(ate)
            if m is None:
                break
            if m.get('saiu') or m.get('fim'):
                return 'saiu' if m.get('saiu') else 'fim'
        while not fila.empty():
            m = fila.get_nowait()
            if m.get('saiu') or m.get('fim'):
                return 'saiu' if m.get('saiu') else 'fim'
        return None

    async def resposta_de(texto: str) -> tuple[str, str]:
        if memoria.eh_privado(texto):
            if local:
                try:
                    return (await local(SISTEMA, texto)).strip() or FRASE_PRIVADO, 'local'
                except Exception as e:  # noqa: BLE001 — o modelo daqui fora: avisa e segue
                    log.info('modo conversa (reserva): o modelo daqui não respondeu: %s', e)
            return FRASE_PRIVADO, 'local'
        try:
            return await responder(conversa, texto) or FRASE_FALHOU, 'groq'
        except Exception as e:  # noqa: BLE001 — a Groq caiu: diz que não deu, sem inventar
            log.info('modo conversa (reserva): a Groq não respondeu: %s', e)
            return FRASE_FALHOU, 'groq'

    leitor = asyncio.ensure_future(ler())
    ultimo = relogio()
    aprendendo = True
    try:
        while True:
            m = await proximo(ultimo + limite)
            if m is None:
                return 'silencio'
            if m.get('saiu') or m.get('fim'):
                return 'saiu' if m.get('saiu') else 'fim'
            if not m.get('audio'):
                continue
            if aprendendo:
                if ouvido.aprender_piso(m['audio']) >= APRENDER_PISO_S:
                    aprendendo = False
                    ouvido.seguir()
                continue
            pedido, wav = False, None
            for tipo, audio in ouvido.alimentar(m['audio']):
                if tipo == 'comando':
                    pedido, wav = True, audio
                    break
            if not pedido:
                if ouvido.fala > 0:
                    ultimo = relogio()  # ele está falando: o silêncio não conta
                continue
            if wav is None:
                ouvido.seguir()  # calado: continua ouvindo, até o silêncio dar o fim
                continue
            t0 = relogio()
            texto = (await transcrever('comando', wav)).strip()
            if not texto:
                ouvido.seguir()
                continue
            await mandar({'tipo': 'ouviu', 'texto': texto})
            resposta, cerebro = await resposta_de(texto)
            await mandar({'tipo': 'disse', 'texto': resposta})
            toca_ate = relogio()
            primeiro_som = None
            try:
                for parte in fala.partes(resposta):
                    async for pcm in falar(parte, conversa):
                        await mandar_audio(pcm)
                        primeiro_som = primeiro_som or relogio() - t0
                        toca_ate = max(toca_ate, relogio()) + len(pcm) / (2 * TAXA_SAIDA)
            except Exception as e:  # noqa: BLE001 — sem voz: o texto já está na tela
                log.info('modo conversa (reserva): a voz não saiu: %s', e)
            log.info('modo conversa (reserva): primeiro som %.1f s depois da fala (%s)',
                     primeiro_som or 0.0, cerebro)
            await ao_turno(texto, resposta, cerebro)
            await mandar({'tipo': 'turno', 'fala': texto, 'resposta': resposta})
            saiu = await esperar_tocar(toca_ate + SOBRA_DA_FALA_S)
            if saiu:
                return saiu
            ultimo = relogio()
            ouvido.seguir()
    finally:
        leitor.cancel()
        await asyncio.gather(leitor, return_exceptions=True)
