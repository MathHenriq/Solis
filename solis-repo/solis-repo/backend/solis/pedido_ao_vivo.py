"""O modo Pedido ao vivo (22/11/2026): "Solis, ..." respondido fala pra fala pelo
Gemini Live, com as ferramentas do Solis, sem o caminho escuta → texto → cérebro
→ voz.

Medido no comparativo (design/testar-live-ferramentas.py): o gemini-3.1-flash-live
acertou 8 de 8 com o primeiro som em 1,9 s (1,2 s sem ferramenta); o caminho de
hoje leva 2,75 s, e 3 a 5 s com pesquisa.

Decisão do Matheus ("Sim, conferindo antes"): o privado é conferido no PC antes
de qualquer coisa ir pro Google. E medido (22/11/2026): o Gemini ouve o áudio no
ritmo da fala — mandado de uma vez no fim (o único jeito de conferir antes),
custava o tempo da própria fala a mais (2,0 a 3,3 s até o primeiro som); o
texto já conferido entrando e a voz saindo, 0,8 a 1,1 s. Então vai o TEXTO: a
escuta acha o fim do pedido, o Whisper transcreve como sempre (transcricao.escuta,
que guarda o privado no PC), o Solis confere, e só o que não é privado vai pra
sessão do Gemini — que já estava aberta desde o "Solis". Nenhum áudio dele sai
pro Google. O privado, a falha e o fim da faixa grátis seguem pelo caminho de hoje.

Ao vivo vão só as ferramentas que não pedem cartão (cotação, clima, jogos, datas,
lembrete, agenda, a busca). Abrir programa, arquivos, skills, ajudantes: o
Gemini chama passar_pro_solis, e o pedido segue pelo caminho de hoje, com os
cartões. Nenhuma função some (as funções são do Solis, não do cérebro)."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import time
from dataclasses import dataclass, field

from . import aprovacoes, banco, corpo, memoria, ollama
from .etapas import MUDA

log = logging.getLogger('solis.pedido_ao_vivo')

MODELO = os.environ.get('SOLIS_PEDIDO_MODELO', 'gemini-3.1-flash-live-preview')
LIGADO = os.environ.get('SOLIS_PEDIDO_AO_VIVO', '1') != '0'
PASSAR = 'passar_pro_solis'
# Sem o primeiro som em tanto tempo depois do fim da fala (sem ferramenta
# rodando), o pedido segue pelo caminho de hoje.
PRIMEIRO_MAX_S = 6.0
TUDO_MAX_S = 45.0
HISTORICO = 8

SISTEMA = (
    'Você é o Solis, o assistente pessoal do Matheus. Ele te chamou pela voz ("Solis, ...") e a sua resposta '
    'vai ser FALADA. Fale em português do Brasil como um assistente competente respondendo em voz alta: direto '
    'ao ponto, natural, em uma a três frases curtas, com a informação que ele pediu. Números em algarismos. O que '
    'você já sabe (fatos, definições, contas) responda direto, sem ferramenta. Use as ferramentas do Solis: '
    'cotação, clima, jogos de um time e conta com datas pelas próprias; lembrete, compromisso e agenda pelas '
    'deles; outra informação de hoje (notícia, preço, o que está em alta), busque com WebFetch num endereço de '
    'busca (https://www.google.com/search?q=...). Pra abrir programa, rodar comando, mexer em arquivo, usar uma '
    'skill, um ajudante, um conector, agendar uma tarefa ou controlar a tela, chame passar_pro_solis com o pedido '
    'e não diga mais nada: o Solis faz pelo caminho completo. Nunca diga que fez algo que a ferramenta não fez.'
)


class Falhou(Exception):
    """O Gemini não respondeu (sem chave, limite, caiu, demorou): o caminho de hoje responde."""


@dataclass
class Resultado:
    fala: str = ''           # o que ele pediu (o texto conferido)
    disse: str = ''          # o que o Solis respondeu (a transcrição da voz)
    passar: str | None = None  # o pedido que vai pelo caminho de hoje (passar_pro_solis)
    ferramentas: list[str] = field(default_factory=list)
    primeiro_som: float | None = None  # segundos do fim da fala até o primeiro som


def ferramentas(c: corpo.Corpo, specs: list[dict]) -> list[dict]:
    """As do kit da voz que não pedem cartão, e o passar_pro_solis."""
    livres = [s for s in specs if s['function']['name'] != corpo.MAIS and (
        s['function']['name'] in aprovacoes.LIVRES
        or (s['function']['name'].startswith(corpo.SOLIS) and s['function']['name'] not in aprovacoes.SOLIS_PEDEM))]
    livres.append({'type': 'function', 'function': {
        'name': PASSAR,
        'description': 'Passa o pedido pro Solis fazer pelo caminho completo (com os cartões de aprovação): abrir '
                       'programa, rodar comando, arquivos, skills, ajudantes, conectores, tarefa agendada, a tela.',
        'parameters': {'type': 'object', 'required': ['pedido'],
                       'properties': {'pedido': {'type': 'string', 'description': 'O pedido dele, como ele disse.'}}}}})
    return livres


def sistema(conversa: int | None) -> str:
    """Quem ele é, a hora, o que o Solis sabe do Matheus e o fim da conversa (só o que não é privado)."""
    memorias = [m for m in banco.memorias() if not m.get('privada')]
    partes = [SISTEMA, 'Agora: ' + time.strftime('%A, %d/%m/%Y, %H:%M') + '.', ollama.contexto(memorias)]
    if conversa is not None:
        msgs = [m for m in banco.mensagens(conversa) if not m.get('privada')][-HISTORICO:]
        if msgs:
            partes.append('A conversa até agora:\n' + '\n'.join(
                f'{"Matheus" if m["papel"] == "pessoa" else "Solis"}: {m["texto"]}' for m in msgs))
    return '\n\n'.join(p for p in partes if p)


def _cliente():
    from google import genai
    from google.genai import types

    from . import apis
    chave = apis._chave_de('gemini')
    if not chave:
        raise Falhou('sem a chave do Gemini')
    return genai.Client(api_key=chave, http_options=types.HttpOptions(api_version='v1beta'))


def disponivel() -> bool:
    from . import apis, conversa_voz
    return LIGADO and apis.tem_chave('gemini') and not conversa_voz.gemini_descansando()


class Sessao:
    """Uma sessão do Gemini Live pra um pedido: aberta quando a escuta ouve o
    "Solis" (`abrir`, em segundo plano: enquanto ele fala, ela conecta) e usada
    quando o pedido acaba (`responder`). `fechar` sempre."""

    def __init__(self, conversa: int | None, voz: str, etapas=MUDA):
        self.conversa, self.voz = conversa, voz
        self.corpo = corpo.Corpo(conversa, etapas, navegar=False, cerebro='gemini-live')
        self.corpo.voz = True
        self._pilha = contextlib.AsyncExitStack()
        self._sessao = None
        self._abrindo: asyncio.Task | None = None

    def abrir(self) -> asyncio.Task:
        if self._abrindo is None:
            self._abrindo = asyncio.ensure_future(self._abrir())
        return self._abrindo

    async def _abrir(self) -> None:
        from google.genai import types
        specs = ferramentas(self.corpo, await self.corpo.especificacoes())
        cfg = types.LiveConnectConfig(
            response_modalities=['AUDIO'],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=self.voz))),
            system_instruction=sistema(self.conversa),
            tools=[types.Tool(function_declarations=[types.FunctionDeclaration(
                name=s['function']['name'], description=s['function']['description'],
                parameters_json_schema=s['function']['parameters']) for s in specs])],
        )
        self._sessao = await self._pilha.enter_async_context(_cliente().aio.live.connect(model=MODELO, config=cfg))

    async def fechar(self) -> None:
        if self._abrindo is not None and not self._abrindo.done():
            self._abrindo.cancel()
        with contextlib.suppress(Exception):
            await self._pilha.aclose()

    async def responder(self, texto: str, enviar_audio, enviar_texto=None) -> Resultado:
        """Manda o pedido (o texto, já conferido) e devolve o que foi dito. Cada
        pedaço da voz (PCM 24 kHz) vai pra `enviar_audio` assim que chega; o que
        ele já disse (o texto da voz, acumulado), pra `enviar_texto`.
        Falhou se não deu pra responder antes do primeiro som."""
        from google.genai import types
        try:
            await asyncio.wait_for(asyncio.shield(self.abrir()), 10)
        except Exception as e:  # noqa: BLE001 — sem a sessão, o caminho de hoje
            raise Falhou(f'não abriu ({type(e).__name__}: {str(e)[:120]})') from e
        s = self._sessao
        r = Resultado(fala=texto)
        try:
            await s.send_client_content(turns=[types.Content(role='user', parts=[types.Part(text=texto)])],
                                        turn_complete=True)
            fim_fala = time.perf_counter()
            async with asyncio.timeout(TUDO_MAX_S):
                acabou = False
                while not acabou:
                    # O primeiro som tem prazo próprio; com ferramenta rodando, ela é que conta.
                    prazo = None if r.primeiro_som is not None else PRIMEIRO_MAX_S
                    async with asyncio.timeout(prazo):
                        async for msg in s.receive():
                            if msg.tool_call:
                                respostas = []
                                for fc in msg.tool_call.function_calls or []:
                                    args = dict(fc.args or {})
                                    if fc.name == PASSAR:
                                        r.passar = str(args.get('pedido') or texto).strip()
                                        return r
                                    r.ferramentas.append(fc.name)
                                    saida = await self.corpo.rodar(fc.name, args)
                                    respostas.append(types.FunctionResponse(id=fc.id, name=fc.name,
                                                                            response={'resultado': saida}))
                                await s.send_tool_response(function_responses=respostas)
                                continue
                            sc = msg.server_content
                            if not sc:
                                continue
                            if sc.output_transcription and sc.output_transcription.text:
                                r.disse += sc.output_transcription.text
                                if enviar_texto is not None:
                                    await enviar_texto(' '.join(r.disse.split()))
                            for parte in (sc.model_turn.parts if sc.model_turn else None) or []:
                                if parte.inline_data and parte.inline_data.data:
                                    if r.primeiro_som is None:
                                        r.primeiro_som = round(time.perf_counter() - fim_fala, 2)
                                    await enviar_audio(parte.inline_data.data)
                            if sc.turn_complete and r.primeiro_som is not None:
                                acabou = True
                                break
        except TimeoutError as e:
            if r.primeiro_som is None:
                raise Falhou('não começou a responder a tempo') from e
            log.info('pedido ao vivo: a resposta passou de %.0f s; parou ali', TUDO_MAX_S)
        except Falhou:
            raise
        except Exception as e:  # noqa: BLE001 — a conexão caiu, o limite, a chave
            if r.primeiro_som is None:
                raise Falhou(f'{type(e).__name__}: {str(e)[:160]}') from e
            log.warning('pedido ao vivo: caiu no meio da resposta (%s)', e)
        r.disse = ' '.join(r.disse.split())
        return r


def privado(texto: str) -> bool:
    return memoria.eh_privado(texto)


# "Solis, vamos conversar": a tela entra no modo Conversa com esse texto (o mesmo
# teste de src/conversaVoz.ts, pedeConversa) — ao vivo, ele nunca chegaria lá.
_PEDE_CONVERSA = re.compile(r'\b(vamos|bora|quero)\s+(conversar|bater\s+(um\s+)?papo)\b|\bmodo\s+conversa\b', re.I)


def pede_conversa(texto: str) -> bool:
    return bool(_PEDE_CONVERSA.search(texto or ''))
