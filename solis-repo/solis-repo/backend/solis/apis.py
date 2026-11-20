"""Cérebros por API, no plano grátis de cada serviço: Groq, Gemini, Mistral e
OpenRouter.

Os quatro falam o mesmo formato de chamada (o `chat/completions` da OpenAI),
então é um código só: cada serviço é um endereço, uma chave e um modelo. Os
endereços foram conferidos nas páginas oficiais em 08/11/2026.

O MODELO NÃO É FIXADO NO CÓDIGO. Os nomes mudam a cada poucos meses e as
próprias documentações se contradizem (a do Mistral diz que mistral-small-latest
é a 3.2 numa página e a 4 em outra). Ao guardar a chave, o Solis pergunta ao
serviço o que existe (`GET /models`) e escolhe pela preferência abaixo; o nome
escolhido fica guardado e aparece na tela.

A chave fica no banco selada pelo cofre (DPAPI): legível só neste usuário do
Windows. Ela nunca volta pro front — a tela só sabe se existe uma.

Grátis tem preço, e a tela diz qual (`nota`): o Gemini grátis pode usar o que
recebe pra melhorar os produtos do Google; o Mistral treina até ser desligado no
console; no OpenRouter quem roda o modelo grátis pode guardar o pedido. O que é
privado nunca chega aqui — o roteador tira antes, como faz pro Claude e o Codex.
"""
import asyncio
import json
import re
import contextlib
import time
from collections.abc import AsyncIterator

import httpx

from . import banco, cofre, conexoes
from .cerebros import CerebroFalhou, pausar
from .etapas import MUDA

PROVEDORES = {
    'groq': {
        'rotulo': 'Groq',
        'base': 'https://api.groq.com/openai/v1',
        'site': 'https://console.groq.com/keys',
        'preferidos': ['openai/gpt-oss-120b', 'llama-3.3-70b-versatile'],
        'nota': 'Grátis, perto de 1.000 pedidos por dia. Modelos abertos, muito rápidos.',
    },
    'gemini': {
        'rotulo': 'Gemini',
        'base': 'https://generativelanguage.googleapis.com/v1beta/openai',
        'site': 'https://aistudio.google.com/apikey',
        'preferidos': [],  # o Flash mais novo, ver _escolher
        'nota': 'Grátis, só os modelos Flash. No grátis o Google pode usar o que você manda pra melhorar os produtos dele.',
    },
    'mistral': {
        'rotulo': 'Mistral',
        'base': 'https://api.mistral.ai/v1',
        'site': 'https://console.mistral.ai/api-keys',
        'preferidos': ['mistral-medium-latest', 'mistral-small-latest'],
        'nota': 'Grátis no plano Experiment. Treina com o que você manda até você desligar em Privacidade, no console.',
    },
    'openrouter': {
        'rotulo': 'OpenRouter',
        'base': 'https://openrouter.ai/api/v1',
        'site': 'https://openrouter.ai/settings/keys',
        # Só os grátis (":free"); entre eles, estes primeiro.
        'preferidos': ['gpt-oss-120b', 'deepseek', 'qwen3', 'llama-3.3-70b'],
        'nota': 'Só os modelos grátis, 50 pedidos por dia. Quem roda o modelo pode guardar o que você manda.',
    },
}

# Pra listar os modelos basta pouco. Pra responder, 60 s sem receber nada (no
# começo ou no meio) é travado — o maior silêncio aceito pros CLIs (cerebros.py).
TIMEOUT_LISTA = httpx.Timeout(15.0, connect=5.0)
TIMEOUT_RESPOSTA = httpx.Timeout(60.0, connect=5.0)
# O primeiro pedaço tem prazo próprio: em 16/11/2026 o Gemini grátis ficou 60 s
# calado até o ReadTimeout, numa resposta por voz. Quem não começa em 15 s está
# falhando, e o próximo cérebro tenta. Entre um pedaço e outro, os 60 s valem.
PRIMEIRO_MAX = 15.0
# Na voz, o prazo é do pedido inteiro até a primeira palavra (não só da primeira
# linha): em 16/11/2026, com a Groq no limite, o Gemini levou 12 s só pra dizer
# 503, e a resposta falada saiu em 22 s. A Groq medida: 0,36 a 2,04 s.
PRIMEIRO_VOZ = 5.0
# Na voz, quanto o gpt-oss pensa antes de responder (None: o padrão dele).
# PROVISÓRIO: medindo tempo e acerto.
RACIOCINIO_NA_VOZ = 'low'


class Limite(CerebroFalhou):
    """O limite grátis do serviço (429), com até quando ele pediu pra esperar."""
    def __init__(self, motivo: str, ate: float | None):
        super().__init__(motivo)
        self.ate = ate


# No meio de uma tarefa com ferramentas, o limite por minuto (medido na Groq
# grátis, 18/11/2026: 8.000 tokens por minuto no gpt-oss-120b, ~3.000 por pedido
# com as ferramentas) espera o que o serviço disse e segue, em vez de largar a
# tarefa no meio. Até este tanto por espera, e estas vezes.
ESPERA_NO_MEIO_MAX = 30.0
ESPERAS_NO_MEIO = 3


class Lotado(CerebroFalhou):
    """O modelo escolhido não atende agora (503 "alta demanda", ou nem começa
    a responder): outro modelo do mesmo serviço pode atender. `por`: quanto
    tempo ele fica de lado."""
    def __init__(self, motivo: str, por: float | None = None):
        super().__init__(motivo)
        self.por = por if por is not None else LOTADO_S


# Medido em 19/11/2026 na conta do Matheus: o gemini-3.8-flash (o escolhido)
# deu 503 "alta demanda" três dias seguidos, e dos 15 Flash da conta só o
# gemini-3-flash-preview e o gemini-3.1-flash-lite responderam. O lotado fica
# de lado este tanto, e a resposta vai no próximo da lista do serviço; o
# cérebro só cai quando nenhum atende.
LOTADO_S = 10 * 60
SUMIU_S = 24 * 3600
TROCAS_MAX = 6
_lotados: dict[tuple[str, str], float] = {}


class ChaveRecusada(Exception):
    """O serviço não aceitou a chave (401/403)."""


class ProvedorFora(Exception):
    """Não deu pra falar com o serviço (rede, erro do lado dele)."""


def _chave_de(nome: str) -> str | None:
    selada = banco.ajuste(f'chave:{nome}')
    if not selada:
        return None
    chave = cofre.abrir(selada)
    return None if chave == cofre.ILEGIVEL else chave


def tem_chave(nome: str) -> bool:
    return nome in PROVEDORES and _chave_de(nome) is not None


def modelo(nome: str) -> str | None:
    return banco.ajuste(f'modelo:{nome}')


def _versao(texto: str) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r'\d+', texto))


def _escolher(nome: str, ids: list[str]) -> str | None:
    """O modelo a usar entre os que o serviço tem agora."""
    if nome == 'gemini':
        # O Flash mais novo que conversa: sem lite, sem áudio/imagem, sem
        # experimental; o estável antes do preview.
        fora = ('lite', 'tts', 'image', 'live', 'audio', 'embedding', 'exp', 'thinking')
        flash = [i for i in ids if 'flash' in i and not any(f in i for f in fora)]
        flash.sort(key=lambda i: ('preview' not in i, _versao(i)), reverse=True)
        return flash[0] if flash else None
    if nome == 'openrouter':
        ids = [i for i in ids if i.endswith(':free')]
        for parte in PROVEDORES[nome]['preferidos']:
            for i in ids:
                if parte in i:
                    return i
        return ids[0] if ids else None
    for preferido in PROVEDORES[nome]['preferidos']:
        if preferido in ids:
            return preferido
    return ids[0] if ids else None


def _reservas_de(nome: str, ids: list[str]) -> list[str]:
    """Os modelos do serviço na ordem de usar, do escolhido pro último (o
    Gemini tem vários Flash, e o grátis é por modelo). Só o Gemini tem reserva."""
    if nome != 'gemini':
        return []
    # Fora também os "omni" (sem cota grátis: 429 desde o primeiro pedido do dia,
    # medido em 19/11/2026) e os "-latest" (apelidos dos que já estão na lista).
    fora = ('tts', 'image', 'live', 'audio', 'embedding', 'exp', 'thinking', 'omni', 'latest')
    flash = [i for i in ids if 'flash' in i and not any(f in i for f in fora)]
    # Os de conversa primeiro, como no _escolher; os lite por último.
    # Pela versão, com ou sem preview: medido em 19/11/2026, o 3-flash-preview
    # atendia e os estáveis 3.5 a 3.8 não, e ele ficava depois de todos.
    flash.sort(key=lambda i: ('lite' not in i, _versao(i), 'preview' not in i), reverse=True)
    return flash


async def _modelo_livre(nome: str, chave: str, preferido: str, cliente=None) -> str | None:
    """O preferido, se não está lotado; senão o próximo da lista do serviço
    (guardada ao salvar a chave; numa chave antiga, pedida ao serviço uma vez)."""
    agora = time.time()
    if _lotados.get((nome, preferido), 0) <= agora:
        return preferido
    reservas = banco.ajuste(f'modelos:{nome}')
    if reservas is None:
        try:
            reservas = _reservas_de(nome, await listar(nome, chave))
        except (ChaveRecusada, ProvedorFora, httpx.HTTPError):
            reservas = []
        banco.guardar_ajuste(f'modelos:{nome}', reservas)
    # A regra de hoje vale também pra uma lista guardada antes dela.
    reservas = _reservas_de(nome, reservas)
    return next((m for m in reservas if _lotados.get((nome, m), 0) <= agora), None)


async def listar(nome: str, chave: str, transporte: httpx.AsyncBaseTransport | None = None) -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_LISTA, transport=transporte) as c:
            r = await c.get(f"{PROVEDORES[nome]['base']}/models", headers={'Authorization': f'Bearer {chave}'})
    except httpx.HTTPError as e:
        raise ProvedorFora(str(e) or type(e).__name__) from e
    if nome == 'gemini' and r.status_code in (401, 403, 404):
        # Há relato de o /models do formato OpenAI do Gemini dar 401 com chave
        # boa (o chat funcionando). Antes de recusar, pergunta pela API nativa.
        return await _listar_gemini_nativo(chave, transporte)
    if r.status_code in (401, 403):
        raise ChaveRecusada()
    if r.status_code >= 400:
        raise ProvedorFora(f'{PROVEDORES[nome]["rotulo"]} respondeu {r.status_code}')
    # O Gemini devolve "models/gemini-...", e o chat aceita sem o prefixo.
    return [m['id'].removeprefix('models/') for m in r.json().get('data', []) if m.get('id')]


async def _listar_gemini_nativo(chave: str, transporte: httpx.AsyncBaseTransport | None) -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_LISTA, transport=transporte) as c:
            r = await c.get(
                'https://generativelanguage.googleapis.com/v1beta/models',
                headers={'x-goog-api-key': chave},
                params={'pageSize': 1000},
            )
    except httpx.HTTPError as e:
        raise ProvedorFora(str(e) or type(e).__name__) from e
    # A API nativa responde 400 ("API key not valid") pra chave errada.
    if r.status_code in (400, 401, 403):
        raise ChaveRecusada()
    if r.status_code >= 400:
        raise ProvedorFora(f'Gemini respondeu {r.status_code}')
    return [
        m['name'].removeprefix('models/')
        for m in r.json().get('models', [])
        if 'generateContent' in m.get('supportedGenerationMethods', ['generateContent'])
    ]


async def guardar_chave(nome: str, chave: str, transporte: httpx.AsyncBaseTransport | None = None) -> str:
    """Confere a chave no próprio serviço, escolhe o modelo e guarda os dois.
    Devolve o modelo. Chave que o serviço recusa não é guardada."""
    ids = await listar(nome, chave, transporte)
    escolhido = _escolher(nome, ids)
    if escolhido is None:
        raise ProvedorFora('nenhum modelo grátis de conversa disponível')
    banco.guardar_ajuste(f'chave:{nome}', cofre.selar(chave))
    banco.guardar_ajuste(f'modelo:{nome}', escolhido)
    banco.guardar_ajuste(f'modelos:{nome}', _reservas_de(nome, ids))
    return escolhido


def apagar_chave(nome: str) -> None:
    banco.apagar_ajuste(f'chave:{nome}')
    banco.apagar_ajuste(f'modelo:{nome}')


def _espera(r: httpx.Response) -> float | None:
    """Até quando (epoch) o serviço pediu pra esperar, se disse."""
    try:
        return time.time() + float(r.headers['retry-after'])
    except (KeyError, ValueError):
        return None


# As tarefas de fundo (o aprendizado com o Ollama fora) esperam mais: ninguém
# está olhando, e o modelo pensa antes.
TIMEOUT_FUNDO = httpx.Timeout(60.0, connect=5.0)
FUNDO_TENTATIVAS = 3
FUNDO_ESPERA_MAX = 30.0


async def responder_json(
    nome: str, sistema: str, prompt: str, esquema: dict, qual: str | None = None,
    transporte: httpx.AsyncBaseTransport | None = None,
) -> dict:
    """Uma resposta presa a um JSON Schema (o response_format da API), inteira,
    sem streaming. `qual`: o modelo (senão, o escolhido pra conversa). Pro
    aprendizado: não pausa o cérebro no limite grátis — quem responde a
    conversa usa outro modelo, e o limite é por modelo."""
    chave = _chave_de(nome)
    escolhido = qual or modelo(nome)
    if not chave or not escolhido:
        raise CerebroFalhou('sem chave')
    corpo = {
        'model': escolhido,
        'messages': [{'role': 'system', 'content': sistema}, {'role': 'user', 'content': prompt}],
        'response_format': {'type': 'json_schema', 'json_schema': {'name': 'resposta', 'schema': esquema}},
    }
    async with contextlib.AsyncExitStack() as pilha:
        c = (conexoes.cliente(nome) if transporte is None
             else await pilha.enter_async_context(httpx.AsyncClient(transport=transporte)))
        for tentativa in range(FUNDO_TENTATIVAS):
            try:
                r = await c.post(f"{PROVEDORES[nome]['base']}/chat/completions", json=corpo,
                                 headers={'Authorization': f'Bearer {chave}'}, timeout=TIMEOUT_FUNDO)
            except httpx.HTTPError as e:
                raise CerebroFalhou(f'{type(e).__name__}: {e}'[:200]) from e
            ultima = tentativa == FUNDO_TENTATIVAS - 1
            if r.status_code == 429 and not ultima:
                # O limite por minuto (medido: ~1.300 tokens de entrada por
                # aprendizado, e o grátis do 20b aguenta 2 a 3 por minuto).
                # Ninguém espera esta resposta: espera o que a Groq disse.
                quando = _espera(r)
                await asyncio.sleep(min(FUNDO_ESPERA_MAX, max(1.0, (quando or time.time() + 10) - time.time())))
                continue
            if r.status_code == 400 and 'json_validate_failed' in r.text and not ultima:
                continue  # o modelo saiu do esquema: de novo, uma vez
            break
    if r.status_code >= 400:
        raise CerebroFalhou(f'respondeu {r.status_code}: {r.text[:200]}')
    try:
        return json.loads(r.json()['choices'][0]['message']['content'])
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise CerebroFalhou(f'não veio JSON: {r.text[:200]}') from e


async def responder(
    nome: str, sistema: str, prompt: str, etapas=MUDA, transporte: httpx.AsyncBaseTransport | None = None,
    rapido: bool = False, corpo=None,
) -> AsyncIterator[str]:
    """A resposta em pedaços, pelo streaming (SSE) do chat/completions.
    `rapido` (a voz): o gpt-oss pensa pouco antes de responder.

    `corpo` (corpo.Corpo): as ferramentas do Solis. O modelo pode pedir uma,
    ela roda aqui (com o cartão, se pede), o resultado volta como mensagem
    `tool`, e ele segue — em rodadas, até responder sem pedir nada."""
    from . import corpo as _corpo
    chave, escolhido = _chave_de(nome), modelo(nome)
    if not chave or not escolhido:
        raise CerebroFalhou('sem chave')
    escolhido = await _modelo_livre(nome, chave, escolhido) or escolhido
    mensagens = [{'role': 'system', 'content': sistema}, {'role': 'user', 'content': prompt}]
    if corpo is not None:
        corpo.transporte = transporte  # o ajudante (Agent) fala pelo mesmo caminho
    ferramentas = await corpo.especificacoes() if corpo is not None else []
    rodadas = _corpo.RODADAS_MAX if ferramentas else 0
    # A conexão guardada (conexoes.py); com um transporte de teste, uma só desta vez.
    async with contextlib.AsyncExitStack() as pilha:
        if transporte is None:
            c = conexoes.cliente(nome)
        else:
            c = await pilha.enter_async_context(httpx.AsyncClient(transport=transporte))
        prazo = PRIMEIRO_VOZ if rapido else None
        try:
            async with asyncio.timeout(prazo) as ate_a_primeira:
                fechando = False
                trocas = 0  # trocas de modelo na resposta inteira
                for rodada in range(rodadas + 1):
                    pedido = {'model': escolhido, 'stream': True, 'messages': mensagens}
                    if ferramentas and not fechando:
                        pedido['tools'] = ferramentas
                    if rapido and RACIOCINIO_NA_VOZ and 'gpt-oss' in escolhido:
                        pedido['reasoning_effort'] = RACIOCINIO_NA_VOZ
                    chamadas: dict[int, dict] = {}
                    dito = ''
                    esperas = 0
                    try:
                        while True:
                            try:
                                async for tipo, valor in _uma_rodada(c, nome, chave, pedido, etapas, rodada == 0):
                                    # Pedir ferramenta também é sinal de vida: o prazo da
                                    # voz vale até a primeira palavra ou a primeira ação.
                                    ate_a_primeira.reschedule(None)
                                    if tipo == 'texto':
                                        dito += valor
                                        yield valor
                                        continue
                                    d = chamadas.setdefault(valor.get('index', 0), {'id': '', 'nome': '', 'args': ''})
                                    f = valor.get('function') or {}
                                    d['id'] = valor.get('id') or d['id']
                                    d['nome'] += f.get('name') or ''
                                    d['args'] += f.get('arguments') or ''
                                    # O Gemini 3 manda a assinatura do raciocínio junto da
                                    # chamada e recusa (400) a rodada seguinte sem ela.
                                    if valor.get('extra_content'):
                                        d['extra'] = valor['extra_content']
                                break
                            except (Lotado, Limite) as e:
                                # No começo (nada dito, nada feito), outro modelo do
                                # mesmo serviço pode atender: o lotado fica de lado.
                                # No Gemini o limite grátis é por modelo, então o 429
                                # também troca.
                                # No meio da tarefa também, no Gemini: a assinatura do
                                # raciocínio de um modelo não vale no outro, então as de
                                # antes viram a que o Google aceita pra histórico (visto em
                                # 19/11/2026: a Wikipédia parou com o modelo lotando na 2ª rodada).
                                trocar_modelo = (not dito and not chamadas and trocas < TROCAS_MAX
                                                 and (rodada == 0 or nome == 'gemini')
                                                 and (isinstance(e, Lotado) or nome == 'gemini'))
                                if trocar_modelo:
                                    _lotados[(nome, escolhido)] = time.time() + getattr(e, 'por', LOTADO_S)
                                    proximo = await _modelo_livre(nome, chave, escolhido)
                                    if proximo and proximo != escolhido:
                                        etapas.marcar('modelo', cerebro=nome, modelo=proximo, antes=escolhido, motivo=str(e))
                                        escolhido = pedido['model'] = proximo
                                        trocas += 1
                                        if rodada > 0:
                                            _sem_assinaturas(mensagens)
                                        continue
                                if isinstance(e, Lotado):
                                    raise
                                # No meio da tarefa (já rodou ferramenta), o limite
                                # por minuto se espera; no começo, cai pro próximo.
                                quanto = (e.ate - time.time()) if e.ate else 10.0
                                if rodada == 0 or esperas == ESPERAS_NO_MEIO or quanto > ESPERA_NO_MEIO_MAX:
                                    pausar(nome, e.ate, 'o limite grátis acabou')
                                    raise
                                esperas += 1
                                etapas.marcar('esperando', cerebro=nome, segundos=round(max(quanto, 1.0), 1))
                                await asyncio.sleep(max(quanto, 1.0))
                    except CerebroFalhou as e:
                        # Já agiu (clicou, anotou): cair pro próximo cérebro
                        # faria de novo. Para aqui, dizendo por quê.
                        if corpo is not None and corpo.agiu:
                            yield f'\n\nParei no meio: {e}.'
                            return
                        raise
                    if not chamadas and not dito and rodada > 0:
                        # Rodou as ferramentas e terminou calado (visto na Groq,
                        # 18/11/2026, depois de 5 ações na Wikipédia): mais um
                        # pedido, sem ferramentas, pra ele dizer o que viu.
                        if not fechando and rodada < rodadas:
                            fechando = True
                            mensagens.append({'role': 'user', 'content': 'Responda ao Matheus agora, com o que você já viu.'})
                            continue
                        yield 'Fiz o caminho, mas não consegui escrever a resposta. Pode pedir de novo?'
                        return
                    if not chamadas:
                        return
                    if rodada == rodadas:
                        yield '\n\nParei: foram muitas ações seguidas sem chegar numa resposta.'
                        return
                    pedidas = [{'id': d['id'] or f'chamada_{rodada}_{i}', 'type': 'function',
                                'function': {'name': d['nome'], 'arguments': d['args'] or '{}'},
                                **_assinatura(nome, d)}
                               for i, d in sorted(chamadas.items())]
                    mensagens.append({'role': 'assistant', 'content': dito or None, 'tool_calls': pedidas})
                    # Vários ajudantes na mesma rodada trabalham ao mesmo tempo (como
                    # os do Claude); o resto, um por vez, na ordem pedida.
                    if len(pedidas) > 1 and all(p['function']['name'] == _corpo.AGENTE for p in pedidas):
                        saidas = await asyncio.gather(*(
                            corpo.rodar(p['function']['name'], _corpo.argumentos(p['function']['arguments']))
                            for p in pedidas))
                    else:
                        saidas = []
                        for p in pedidas:
                            saidas.append(await corpo.rodar(p['function']['name'],
                                                            _corpo.argumentos(p['function']['arguments'])))
                    for p, saida in zip(pedidas, saidas):
                        mensagens.append({'role': 'tool', 'tool_call_id': p['id'], 'content': saida})
        except TimeoutError as e:
            raise CerebroFalhou(f'não começou a responder em {prazo:.0f} s') from e
        except httpx.HTTPError as e:
            raise CerebroFalhou(f'{type(e).__name__}: {e}'[:200]) from e


def _assinatura(nome: str, chamada: dict) -> dict:
    """O que volta junto de cada chamada de ferramenta na rodada seguinte: a
    assinatura do raciocínio do Gemini 3 (`extra_content.google.thought_signature`),
    sem a qual ele recusa com 400 ("Function call is missing a thought_signature",
    visto em 19/11/2026). Sem ela na chamada, o valor que o próprio Google aceita
    pra histórico sem assinatura."""
    if chamada.get('extra'):
        return {'extra_content': chamada['extra']}
    if nome == 'gemini':
        return {'extra_content': {'google': {'thought_signature': 'skip_thought_signature_validator'}}}
    return {}


def _sem_assinaturas(mensagens: list[dict]) -> None:
    """Trocou de modelo no meio da tarefa: as assinaturas do anterior viram a
    que o Google aceita pra histórico sem assinatura."""
    for m in mensagens:
        for chamada in m.get('tool_calls') or []:
            chamada['extra_content'] = {'google': {'thought_signature': 'skip_thought_signature_validator'}}


@contextlib.asynccontextmanager
async def _fechar(r: httpx.Response):
    try:
        yield r
    finally:
        await r.aclose()


async def _uma_rodada(c: httpx.AsyncClient, nome: str, chave: str, pedido: dict, etapas, primeira_rodada: bool):
    """Um pedido ao chat/completions: ('texto', pedaço) e ('chamada', parte de
    um tool_call) conforme chegam."""
    pedir = c.build_request('POST', f"{PROVEDORES[nome]['base']}/chat/completions",
                            headers={'Authorization': f'Bearer {chave}'}, json=pedido, timeout=TIMEOUT_RESPOSTA)
    try:
        # O começo da resposta tem prazo na primeira rodada: medido no Gemini
        # (19/11/2026), modelo lotado ficava 60 s calado até o ReadTimeout.
        # Depois das ferramentas o pedido é maior: o dobro do prazo.
        async with asyncio.timeout(PRIMEIRO_MAX if primeira_rodada else 2 * PRIMEIRO_MAX):
            r = await c.send(pedir, stream=True)
    except (TimeoutError, httpx.TimeoutException) as e:
        raise Lotado(f'não começou a responder em {PRIMEIRO_MAX:.0f} s') from e
    async with _fechar(r):
        if primeira_rodada:
            etapas.marcar('pedido', cerebro=nome)
        if r.status_code == 429:
            raise Limite('o limite grátis acabou', _espera(r))
        if r.status_code == 503:
            await r.aread()
            raise Lotado('o modelo está lotado (503)')
        if r.status_code == 404:
            # "Não está mais disponível pra novos usuários" (o gemini-2.5-flash,
            # 19/11/2026): fica de lado um dia.
            await r.aread()
            raise Lotado('o modelo não existe mais pra esta conta (404)', SUMIU_S)
        if r.status_code in (401, 403):
            pausar(nome, time.time() + 24 * 3600, 'a chave foi recusada')
            raise CerebroFalhou('a chave foi recusada')
        if r.status_code >= 400:
            await r.aread()
            raise CerebroFalhou(f'respondeu {r.status_code}: {r.text[:160]}')
        pensou = False
        linhas = r.aiter_lines()
        primeira = True
        while True:
            try:
                if primeira:
                    linha = await asyncio.wait_for(anext(linhas), PRIMEIRO_MAX)
                    primeira = False
                else:
                    linha = await anext(linhas)
            except StopAsyncIteration:
                return
            except asyncio.TimeoutError as e:
                raise CerebroFalhou(f'não começou a responder em {PRIMEIRO_MAX:.0f} s') from e
            if not linha.startswith('data:'):
                continue
            dado = linha[5:].strip()
            if dado == '[DONE]':
                return
            try:
                delta = json.loads(dado)['choices'][0].get('delta', {})
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            # Modelos que raciocinam mandam o raciocínio à parte; não vai
            # pra tela, só o fato de que está pensando.
            if not pensou and (delta.get('reasoning') or delta.get('reasoning_content')):
                etapas.marcar('pensando', cerebro=nome)
                pensou = True
            for chamada in delta.get('tool_calls') or []:
                yield 'chamada', chamada
            if delta.get('content'):
                yield 'texto', delta['content']
