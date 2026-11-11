"""Conversa com o Ollama — o que está instalado, o que está carregado, e o chat.

Só fala HTTP com o servidor do Ollama (padrão 127.0.0.1:11434). Não formata
nada pra tela: devolve bytes e números crus, e quem decide "4,7 GB" ou "128k"
é o front.
"""
import asyncio
import base64
import json
import logging
import os
from datetime import date, datetime
from collections.abc import AsyncIterator

import httpx

from .etapas import MUDA

log = logging.getLogger('solis.ollama')

OLLAMA = os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434')

# ERROR_STATES.md §2 pede timeout de 8–10s antes de desistir do modelo local.
# A conexão em si falha rápido: se nada escuta na porta, não adianta esperar 8s
# pra dizer que o Ollama está fora do ar.
TIMEOUT = httpx.Timeout(8.0, connect=2.0)

# Na conversa os 8s não servem: o primeiro pedaço só sai depois que o Ollama
# carrega o modelo na memória, e um 14B frio passa disso fácil. O limite vale
# ENTRE pedaços — um modelo que travou no meio ainda é cortado, só que em 2 min.
TIMEOUT_CONVERSA = httpx.Timeout(120.0, connect=2.0)
# Rodadas de ferramenta numa resposta: na medição o qwen3:8b usou no máximo 4
# (buscar, listar, listar, ler). Passou disso, ele está andando em círculo.
RODADAS_MAX = 6

# Quem o Solis é e, sobretudo, o que ele NÃO consegue fazer. O modelo não sabe
# o que o app em volta dele faz: sem esta lista, perguntado se tem internet, ele
# inventa que tem (aconteceu, com o llama3.2:3b). Este texto descreve as
# capacidades de HOJE — quando ferramentas entrarem, ele muda junto.
SISTEMA = (
    'Você é o Solis, o assistente pessoal do Matheus. Você roda localmente no '
    'computador dele, num modelo de linguagem pequeno.\n\n'
    'O que você NÃO pode fazer, e deve dizer com clareza quando perguntarem: '
    'acessar a internet e ler arquivos ou programas do computador. De outras '
    'conversas, você só sabe o que estiver nas memórias abaixo. Fora isso, você '
    'só sabe o que foi dito nesta conversa e o que aprendeu no treinamento.\n\n'
    'Quando o Matheus pedir pra guardar ou lembrar algo, isso fica guardado nas '
    'memórias — pode confirmar que guardou.\n\n'
    'Quando ele disser algo que precisa fazer ("me lembra de pagar a luz dia 15", '
    '"tenho que entregar o relatório sexta"), depois da sua resposta isso vira uma '
    'tarefa na tela Tarefas, com o prazo — pode dizer que ficou anotado. Com hora ("daqui a '
    '30 minutos", "às 15h"), o Solis avisa no Windows na hora: confirme com a hora certa, '
    'contando a partir de Agora — por exemplo, se Agora é 10:12 e ele pede "daqui a 30 minutos", '
    'responda "Anotado, te aviso às 10:42". Marcar como '
    'feita, mudar ou apagar uma tarefa você não consegue: é pela tela Tarefas. Do mesmo '
    'jeito, compromisso com dia marcado ("quinta às 15h tenho consulta") vai pra tela Agenda.\n\n'
    'Quando não souber algo, diga que não sabe. Responda em português do Brasil, '
    'com clareza e sem rodeios.'
)


# Quem é o "outro lado" num trecho antigo. Conversa importada do ChatGPT tem
# o ChatGPT respondendo, não o Solis — e o modelo precisa saber quem disse.
AUTORES = {'solis': 'Solis', 'chatgpt': 'ChatGPT', 'claude': 'Claude'}


def autor(trecho: dict) -> str:
    return 'Matheus' if trecho['papel'] == 'pessoa' else AUTORES.get(trecho.get('origem'), 'Solis')


def contexto(memorias: list[dict], trechos: list[dict] | None = None, resumo: str | None = None) -> str:
    """O que o Solis sabe que importa pra esta mensagem — o mesmo bloco serve o
    prompt do modelo local e o que vai pros cérebros de nuvem."""
    # Agora, no relógio do computador: "que horas são?", "daqui a 30 minutos" e
    # "amanhã" dependem disso — sem esta linha, o Claude respondia que não via a hora.
    agora = datetime.now()
    partes = [f'Agora: {DIAS[agora.weekday()]}, {agora:%d/%m/%Y}, {agora:%H:%M}.']
    if memorias:
        partes.append('Memórias sobre o Matheus:\n' + '\n'.join(f'- {m["texto"]}' for m in memorias))
    else:
        partes.append('Ainda não há memórias guardadas.')
    if resumo:
        partes.append(
            'Resumo do começo desta conversa (essas mensagens não estão mais abaixo, '
            'só este resumo delas):\n' + resumo
        )
    # Os trechos dos arquivos (Conhecimento) vêm na mesma lista, marcados.
    arquivos = [t for t in trechos or [] if t.get('arquivo')]
    tarefas = [t for t in trechos or [] if t.get('tarefa')]
    agenda = [t for t in trechos or [] if t.get('compromisso')]
    lembrete = next((t for t in trechos or [] if t.get('lembrete')), None)
    conversas = [
        t for t in trechos or [] if not t.get('arquivo') and not t.get('tarefa') and not t.get('compromisso') and not t.get('lembrete')
    ]
    if lembrete:
        # memoria.hora_pedida: a conta feita em código, a mesma que vai pro aviso.
        # Só a relativa ("daqui a 30 minutos") traz o dia; em "quinta às 15h" o
        # dia é o que ele disse.
        dia = ''
        if lembrete.get('relativa'):
            dia = 'hoje ' if lembrete['dia'] == agora.date().isoformat() else 'amanhã '
        partes.append(
            f'Esta mensagem pede um lembrete: a hora, já calculada pelo Solis, é {dia}às '
            f'{lembrete["hora"]}. Use esta hora na resposta, sem refazer a conta.'
        )
    if conversas:
        # Com data e autor: "o Solis disse" e "o Matheus disse" pesam diferente,
        # e "em março" responde "quando a gente falou disso?". O texto vai numa
        # linha só: uma resposta antiga com lista viraria itens soltos no meio
        # desta lista, misturados com ela.
        linhas = [f'- [{t["criada"][:10]}] {autor(t)}: {" ".join(t["texto"].split())}' for t in conversas]
        partes.append(
            'Trechos de conversas antigas que parecem ligados a esta mensagem '
            '(use se ajudarem; ignore se não):\n' + '\n'.join(linhas)
        )
    if arquivos:
        # Com o nome do arquivo e a página: o modelo pode dizer de onde tirou, e
        # o Matheus conferir no original.
        linhas = [f'- [{_fonte(a)}] {a["texto"]}' for a in arquivos]
        partes.append(
            'Trechos dos arquivos que o Matheus deu pro Solis ler (Conhecimento). Use se '
            'ajudarem e diga de qual arquivo veio; ignore se não:\n' + '\n'.join(linhas)
        )
    if tarefas:
        hoje = date.today()
        linhas = [f'- [{_quando(t)}] {t["texto"]}' for t in tarefas]
        partes.append(
            f'Tarefas abertas do Matheus (hoje é {DIAS[hoje.weekday()]}, {hoje:%d/%m/%Y}), da mais '
            'próxima pra mais longe:\n' + '\n'.join(linhas)
        )
    if agenda:
        hoje = date.today()
        linhas = [f'- [{_quando({"prazo": c["dia"], "hora": c["hora"]})}] {c["texto"]}' for c in agenda]
        partes.append(
            f'Agenda do Matheus, de hoje ({DIAS[hoje.weekday()]}, {hoje:%d/%m/%Y}) aos próximos 7 dias:\n'
            + '\n'.join(linhas)
        )
    return '\n\n'.join(partes)


DIAS = ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado', 'domingo']


def _quando(tarefa: dict) -> str:
    if not tarefa.get('prazo'):
        return 'sem prazo'
    d = date.fromisoformat(tarefa['prazo'])
    return f'{DIAS[d.weekday()]} {d:%d/%m}' + (f' às {tarefa["hora"]}' if tarefa.get('hora') else '')


def _fonte(arquivo: dict) -> str:
    if arquivo.get('url'):
        return f'{arquivo["nome"]}, {arquivo["url"]}'
    return f'{arquivo["nome"]}, pág. {arquivo["pagina"]}' if arquivo.get('pagina') else arquivo['nome']


# Com a ferramenta Arquivos ligada (pc.py), a frase do que ele NÃO pode muda:
# com ela no lugar, o qwen3:8b respondia "não tenho acesso a arquivos" sem
# tentar (4 de 12 perguntas sobre arquivos, medido).
NAO_PODE = 'acessar a internet e ler arquivos ou programas do computador.'
NAO_PODE_COM_ARQUIVOS = (
    'acessar a internet, rodar programas e criar, mudar ou apagar arquivos. Ler arquivos você '
    'pode, nas pastas que o Matheus autorizou.'
)


# Quando a mensagem veio pela voz e a resposta vai ser falada (pedido do
# Matheus: "fala demais, só repete; tem que ser mais direto, mais rápido").
VOZ = (
    'Esta mensagem veio pela voz e a sua resposta vai ser FALADA. Responda em uma ou duas frases '
    'curtas e diretas, como alguém respondendo em voz alta: sem listas, sem títulos, sem '
    'markdown, sem repetir a pergunta e sem oferecer alternativas que ninguém pediu.'
)


def sistema(
    memorias: list[dict], trechos: list[dict] | None = None, resumo: str | None = None, arquivos: bool = False,
    voz: bool = False,
) -> str:
    texto = _sistema(memorias, trechos, resumo, arquivos)
    return f'{texto}\n\n{VOZ}' if voz else texto


def _sistema(memorias, trechos, resumo, arquivos) -> str:
    if not arquivos:
        return f'{SISTEMA}\n\n{contexto(memorias, trechos, resumo)}'
    from . import pc
    base = SISTEMA.replace(NAO_PODE, NAO_PODE_COM_ARQUIVOS).replace(
        'Quando não souber algo, diga que não sabe.',
        'Quando não souber algo da vida dele, procure nos arquivos; se não achar, diga que não sabe.',
    )
    return f'{base}\n\n{pc.INSTRUCAO}\n\n{contexto(memorias, trechos, resumo)}'


PAPEIS = {'pessoa': 'user', 'solis': 'assistant'}


class OllamaIndisponivel(Exception):
    """O Ollama não respondeu — desligado, porta errada ou travado."""


class ModeloInexistente(Exception):
    """O modelo pedido não está instalado no Ollama."""


def _contexto(info: dict) -> int | None:
    # A chave é prefixada pela arquitetura ("llama.context_length",
    # "qwen2.context_length", "nomic-bert.context_length"), então procura pelo sufixo.
    for chave, valor in info.items():
        if chave.endswith('.context_length'):
            return int(valor)
    return None


def _embeddings(nome: str, detalhes: dict) -> bool:
    # Ollama recente declara `capabilities`; versões antigas não, e aí o nome é
    # o único sinal que sobra (nomic-embed-text, mxbai-embed-large...).
    capacidades = detalhes.get('capabilities')
    if capacidades is not None:
        return 'embedding' in capacidades
    return 'embed' in nome


async def instalados(transporte: httpx.AsyncBaseTransport | None = None) -> set[str]:
    """Só os nomes, numa chamada só: pra decidir qual modelo usar não precisa
    dos detalhes de cada um que o listar_modelos busca."""
    try:
        async with httpx.AsyncClient(base_url=OLLAMA, timeout=TIMEOUT, transport=transporte) as c:
            r = await c.get('/api/tags')
            r.raise_for_status()
    except httpx.HTTPError as e:
        raise OllamaIndisponivel() from e
    return {m['name'] for m in r.json().get('models', [])}


async def listar_modelos(transporte: httpx.AsyncBaseTransport | None = None) -> list[dict]:
    async with httpx.AsyncClient(base_url=OLLAMA, timeout=TIMEOUT, transport=transporte) as c:
        try:
            tags, ps = await asyncio.gather(c.get('/api/tags'), c.get('/api/ps'))
            tags.raise_for_status()
        except httpx.HTTPError as e:
            raise OllamaIndisponivel() from e

        modelos = tags.json().get('models', [])
        carregados = {m['name'] for m in ps.json().get('models', [])} if ps.is_success else set()

        # /api/show é por modelo; em paralelo, porque com 5 modelos em série a
        # tela esperaria 5 idas e voltas. Se um falhar, o modelo ainda aparece
        # — só sem contexto.
        async def mostrar(nome: str) -> dict:
            try:
                r = await c.post('/api/show', json={'model': nome})
                return r.json() if r.is_success else {}
            except httpx.HTTPError:
                return {}

        detalhes = await asyncio.gather(*(mostrar(m['name']) for m in modelos))

    return [
        {
            'nome': m['name'],
            'bytes': m.get('size', 0),
            'quantizacao': m.get('details', {}).get('quantization_level'),
            'contexto': _contexto(d.get('model_info', {})),
            # Na memória agora (/api/ps). Não é o "Em uso" da tela — esse é o
            # modelo escolhido pra Conversa, e quem guarda a escolha é o front.
            # O Ollama descarrega o modelo depois de ~5 min parado.
            'carregado': m['name'] in carregados,
            'embeddings': _embeddings(m['name'], d),
        }
        for m, d in zip(modelos, detalhes)
    ]


async def conversar(
    modelo: str,
    mensagens: list[dict],
    memorias: list[dict] | None = None,
    trechos: list[dict] | None = None,
    resumo: str | None = None,
    transporte: httpx.AsyncBaseTransport | None = None,
    etapas=MUDA,
    ferramentas: bool = False,
    conversa: int | None = None,
    voz: bool = False,
    pensar: bool | None = None,
) -> AsyncIterator[str]:
    """Abre a resposta do modelo e devolve os pedaços de texto conforme saem.
    Com `ferramentas`, o modelo pode ler os arquivos das pastas autorizadas
    (pc.py), em rodadas, e cada uso vira a etapa `ferramenta`.

    O erro de conexão e o de modelo inexistente são levantados AQUI, antes do
    primeiro pedaço — depois que o streaming começa já não dá pra trocar o
    status da resposta HTTP. Um corte no meio só encerra o texto onde parou.
    """
    mensagens_ollama = [{'role': 'system', 'content': sistema(memorias or [], trechos, resumo, arquivos=ferramentas, voz=voz)}] + [
        {'role': PAPEIS[m['papel']], 'content': m['texto']} for m in mensagens
    ]
    corpo = {'model': modelo, 'stream': True, 'messages': mensagens_ollama}
    # `pensar=False` desliga o raciocínio (qwen3): a voz rápida (roteador).
    if pensar is not None:
        corpo['think'] = pensar
    if voz:
        corpo['keep_alive'] = FICA_NA_VOZ
    if ferramentas:
        from . import pc
        corpo['tools'] = pc.FERRAMENTAS
    cliente = httpx.AsyncClient(base_url=OLLAMA, timeout=TIMEOUT_CONVERSA, transport=transporte)

    async def abrir():
        try:
            r = await cliente.send(cliente.build_request('POST', '/api/chat', json=corpo), stream=True)
        except httpx.HTTPError as e:
            raise OllamaIndisponivel() from e
        if r.status_code == 404:
            await r.aclose()
            raise ModeloInexistente()
        if not r.is_success:
            await r.aclose()
            raise OllamaIndisponivel()
        return r

    try:
        r = await abrir()
    except (OllamaIndisponivel, ModeloInexistente):
        await cliente.aclose()
        raise

    async def pedacos() -> AsyncIterator[str]:
        nonlocal r
        pensou = False
        try:
            # Com as ferramentas (pc.py), uma resposta pode ter várias rodadas: o
            # modelo pede uma ferramenta, ela roda aqui, o resultado volta como
            # mensagem `tool`, e ele segue — até responder sem pedir nada.
            for rodada in range(RODADAS_MAX + 1):
                chamadas: list[dict] = []
                dito = ''
                # Um JSON por linha. Modelos que "pensam" (qwen3) mandam o raciocínio
                # em `message.thinking`; só `content` é resposta, o resto fica de fora.
                async for linha in r.aiter_lines():
                    if not linha:
                        continue
                    parte = json.loads(linha)
                    if 'error' in parte:
                        break
                    msg = parte.get('message', {})
                    chamadas += msg.get('tool_calls') or []
                    texto = msg.get('content', '')
                    if msg.get('thinking') and not pensou:
                        etapas.marcar('pensando', cerebro='local')
                        pensou = True
                    if texto:
                        dito += texto
                        yield texto
                    if parte.get('done'):
                        # Os tempos do Ollama, pra achar a próxima demora: o
                        # 9,5 s até a primeira palavra visto em 11/11/2026 não
                        # se repetiu medido de fora.
                        seg = lambda k: (parte.get(k) or 0) / 1e9  # noqa: E731
                        if seg('total_duration') > 3:
                            log.info('ollama %s: carregar %.1fs, ler o pedido %.1fs (%s tokens), escrever %.1fs',
                                     modelo, seg('load_duration'), seg('prompt_eval_duration'),
                                     parte.get('prompt_eval_count'), seg('eval_duration'))
                        break
                await r.aclose()
                if not chamadas:
                    return
                if rodada == RODADAS_MAX:
                    yield '\n\nParei de procurar: foram muitas tentativas seguidas sem chegar numa resposta.'
                    return
                from . import pc
                mensagens_ollama.append({'role': 'assistant', 'content': dito, 'tool_calls': chamadas})
                for c in chamadas:
                    f = c.get('function') or {}
                    nome, argumentos = f.get('name', ''), f.get('arguments') or {}
                    saida, ok = await asyncio.to_thread(pc.rodar, nome, argumentos, conversa)
                    etapas.marcar('ferramenta', ferramenta=nome, alvo=pc.alvo(argumentos), ok=ok)
                    mensagens_ollama.append({'role': 'tool', 'content': saida, 'tool_name': nome})
                try:
                    r = await abrir()
                except (OllamaIndisponivel, ModeloInexistente):
                    return
        except httpx.HTTPError:
            pass
        finally:
            await r.aclose()
            await cliente.aclose()

    return pedacos()


# Quanto o modelo fica na GPU depois de usado pela voz: o padrão do Ollama são
# 5 minutos, e a segunda pergunta de uma conversa falada costuma vir depois.
FICA_NA_VOZ = '15m'


async def aquecer(modelo: str, transporte: httpx.AsyncBaseTransport | None = None) -> None:
    """Carrega o modelo na GPU sem perguntar nada (um /api/chat sem mensagens).
    Erro aqui não importa: é só pra adiantar."""
    try:
        async with httpx.AsyncClient(base_url=OLLAMA, timeout=TIMEOUT_CONVERSA, transport=transporte) as c:
            await c.post('/api/chat', json={'model': modelo, 'messages': [], 'keep_alive': FICA_NA_VOZ})
    except httpx.HTTPError:
        pass


async def _perguntar(
    modelo: str,
    instrucao: str,
    texto: str,
    formato: dict | None,
    transporte: httpx.AsyncBaseTransport | None,
    pensar: bool | None = None,
) -> str:
    """Uma pergunta só, sem streaming. Temperatura 0: extração e resumo não são
    lugar de criatividade — a mesma conversa tem que dar o mesmo resultado.

    `pensar=False` desliga o raciocínio dos modelos que pensam (qwen3): pra uma
    tarefa curta ele só custa tempo — o título levava de 5 a 22 s com ele e
    0,2 a 0,4 s sem (medido). Nos que não pensam, não muda nada."""
    corpo = {
        'model': modelo,
        'stream': False,
        'options': {'temperature': 0},
        'messages': [{'role': 'system', 'content': instrucao}, {'role': 'user', 'content': texto}],
    }
    if pensar is not None:
        corpo['think'] = pensar
    # O título e o aprendizado usam o mesmo modelo da conversa: sem isto, eles
    # devolviam o prazo dele pro padrão do Ollama (5 min), e a próxima pergunta
    # pela voz esperava o modelo subir de novo (9,4 s medidos no app).
    corpo['keep_alive'] = FICA_NA_VOZ
    if formato:
        corpo['format'] = formato
    try:
        async with httpx.AsyncClient(base_url=OLLAMA, timeout=TIMEOUT_CONVERSA, transport=transporte) as c:
            r = await c.post('/api/chat', json=corpo)
    except httpx.HTTPError as e:
        raise OllamaIndisponivel() from e
    if r.status_code == 404:
        raise ModeloInexistente()
    if not r.is_success:
        raise OllamaIndisponivel()
    return r.json()['message']['content']


async def responder_json(
    modelo: str,
    instrucao: str,
    texto: str,
    esquema: dict,
    transporte: httpx.AsyncBaseTransport | None = None,
) -> dict:
    """Resposta presa a um JSON Schema. `format` com esquema obriga o Ollama a
    gerar JSON válido nesse formato — sem isso um modelo pequeno devolve
    "Claro! Aqui está o JSON:" antes do JSON."""
    return json.loads(await _perguntar(modelo, instrucao, texto, esquema, transporte))


async def responder_texto(
    modelo: str,
    instrucao: str,
    texto: str,
    transporte: httpx.AsyncBaseTransport | None = None,
    pensar: bool | None = None,
) -> str:
    return await _perguntar(modelo, instrucao, texto, None, transporte, pensar)


async def ler_imagem(
    modelo: str,
    imagem: bytes,
    instrucao: str,
    transporte: httpx.AsyncBaseTransport | None = None,
) -> tuple[str, bool]:
    """(texto, cortado) de um modelo de visão. `cortado` = bateu no limite de
    saída, que num OCR quer dizer repetição: nenhuma página tem 4096 tokens.

    Sem raciocínio (o qwen3.5 pensa por padrão, e transcrever não precisa) e
    com 8192 de contexto: uma página A4 a 150 dpi já é mais de mil tokens de
    imagem, e o padrão do Ollama cortaria a resposta de uma página cheia."""
    corpo = {
        'model': modelo,
        'stream': False,
        'think': False,
        'options': {'temperature': 0, 'num_ctx': 8192, 'num_predict': 4096},
        'messages': [{'role': 'user', 'content': instrucao, 'images': [base64.b64encode(imagem).decode()]}],
    }
    try:
        async with httpx.AsyncClient(base_url=OLLAMA, timeout=TIMEOUT_CONVERSA, transport=transporte) as c:
            r = await c.post('/api/chat', json=corpo)
            if r.status_code == 400 and 'think' in r.text:
                # Modelo de visão que não pensa (gemma3) recusa o `think`.
                del corpo['think']
                r = await c.post('/api/chat', json=corpo)
    except httpx.HTTPError as e:
        raise OllamaIndisponivel() from e
    if r.status_code == 404:
        raise ModeloInexistente()
    if not r.is_success:
        raise OllamaIndisponivel()
    dados = r.json()
    return dados['message']['content'], dados.get('done_reason') == 'length'


async def embeddings(
    modelo: str,
    textos: list[str],
    transporte: httpx.AsyncBaseTransport | None = None,
) -> list[list[float]]:
    """Um vetor por texto, na mesma ordem (/api/embed aceita a lista inteira)."""
    try:
        async with httpx.AsyncClient(base_url=OLLAMA, timeout=TIMEOUT_CONVERSA, transport=transporte) as c:
            r = await c.post('/api/embed', json={'model': modelo, 'input': textos})
    except httpx.HTTPError as e:
        raise OllamaIndisponivel() from e
    if r.status_code == 404:
        raise ModeloInexistente()
    if not r.is_success:
        raise OllamaIndisponivel()
    return r.json()['embeddings']
