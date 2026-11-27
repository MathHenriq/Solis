"""O PC como corpo do servidor (26/11/2026): o cérebro na nuvem usa o PC ligado.

O Solis do celular pensa no servidor, mas a tela, os arquivos e o terminal são
do PC. Quando o PC está ligado (e o Matheus deixou, em Configurações → Servidor),
ele mesmo liga pro servidor — por um WebSocket de saída, com a senha do servidor:
nada no PC fica aberto pra internet. Daí o cérebro do servidor ganha as
ferramentas do PC, com os mesmos nomes de sempre, e quem executa é o PC.

A aprovação acontece onde o Matheus está: o cartão aparece na conversa do
servidor (no celular), como qualquer outro; o PC executa o que já veio aprovado,
e anota no registro de ações dele, como sempre. O próprio PC ainda manda no que
oferece: só as pastas autorizadas, a tela só com o Controle da tela ligado, e
nada disso sem a chave "Deixar o servidor usar este PC".

Nesta primeira parte vão o terminal, os arquivos das pastas autorizadas e ler a
tela. Clicar e digitar na tela de longe ficam pra próxima: o cartão delas mostra
um print do lugar do clique, que tem de vir do PC antes da aprovação.

Protocolo (JSON):
  PC → servidor  {"tipo": "ola", "pc": nome, "terminal": bool, "tela": bool, "arquivos": bool}
  servidor → PC  {"tipo": "pedido", "id", "ferramenta", "entrada"}
  PC → servidor  {"tipo": "resposta", "id", "saida", "ok"}
  os dois        {"tipo": "pulso"}  (a cada PULSO s, pra o túnel não derrubar a ligação parada)
"""
import asyncio
import json
import logging
import os
import platform
import uuid

from . import banco, cofre

log = logging.getLogger('solis.corpo_remoto')

PULSO = 25            # segundos entre um pulso e outro
PRAZO_PADRAO = 60.0   # segundos esperando o PC responder um pedido
TELA_LER = 'mcp__solis__tela_ler'
# Só estas viajam (o PC recusa o resto, mesmo que o servidor peça).
TERMINAL = 'PowerShell'
ARQUIVOS = {'mcp__solis__listar_pasta', 'mcp__solis__buscar_arquivos', 'mcp__solis__ler_arquivo'}
DE_LONGE = {TERMINAL, TELA_LER} | ARQUIVOS


class PcFora(Exception):
    """O PC não está ligado no servidor (ou caiu no meio do pedido)."""


# — No servidor ———————————————————————————————————————————————————————————————

class _Ligacao:
    def __init__(self, ws, capacidades: dict):
        self.ws, self.capacidades = ws, capacidades
        self.pendentes: dict[str, asyncio.Future] = {}


_pc: _Ligacao | None = None


def conectado() -> dict | None:
    """As capacidades do PC ligado agora, ou None."""
    return dict(_pc.capacidades) if _pc else None


async def chamar(ferramenta: str, entrada: dict, prazo: float = PRAZO_PADRAO) -> tuple[str, bool]:
    """Pede ao PC; (saida, ok). PcFora se ele não está, não responde ou caiu."""
    ligacao = _pc
    if ligacao is None:
        raise PcFora('o PC não está ligado no servidor')
    id_ = uuid.uuid4().hex[:12]
    futuro = asyncio.get_running_loop().create_future()
    ligacao.pendentes[id_] = futuro
    try:
        await ligacao.ws.send_json({'tipo': 'pedido', 'id': id_, 'ferramenta': ferramenta, 'entrada': entrada})
        resposta = await asyncio.wait_for(futuro, prazo)
    except asyncio.TimeoutError as e:
        raise PcFora(f'o PC não respondeu em {prazo:.0f} s') from e
    finally:
        ligacao.pendentes.pop(id_, None)
    return str(resposta.get('saida') or ''), bool(resposta.get('ok'))


async def atender(ws) -> None:
    """A rota /corpo do servidor: o PC liga aqui (já passou pela senha, nuvem.Porteiro)."""
    global _pc
    await ws.accept()
    try:
        ola = await asyncio.wait_for(ws.receive_json(), 15)
    except Exception:  # noqa: BLE001 — não se apresentou: fora
        await ws.close(code=1008)
        return
    if ola.get('tipo') != 'ola':
        await ws.close(code=1008)
        return
    capacidades = {k: bool(ola.get(k)) for k in ('terminal', 'tela', 'arquivos')}
    capacidades['pc'] = str(ola.get('pc') or 'PC')[:60]
    anterior, _pc = _pc, _Ligacao(ws, capacidades)
    minha = _pc
    if anterior is not None:
        _falhar_pendentes(anterior, 'o PC ligou de novo')
        try:
            await anterior.ws.close()
        except Exception:  # noqa: BLE001
            pass
    log.info('corpo: %s ligado (%s)', capacidades['pc'], ', '.join(k for k, v in capacidades.items() if v is True) or 'nada')
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get('tipo') == 'resposta':
                futuro = minha.pendentes.get(str(msg.get('id')))
                if futuro:
                    _entregar(futuro, resultado=msg)
            elif msg.get('tipo') == 'pulso':
                await ws.send_json({'tipo': 'pulso'})
            elif msg.get('tipo') == 'ola':  # o PC mudou o que oferece (ligou a tela...)
                minha.capacidades.update({k: bool(msg.get(k)) for k in ('terminal', 'tela', 'arquivos')})
    except Exception:  # noqa: BLE001 — caiu (WebSocketDisconnect e afins)
        pass
    finally:
        if _pc is minha:
            _pc = None
            log.info('corpo: %s desligou', capacidades['pc'])
        _falhar_pendentes(minha, 'o PC desligou no meio')


def _entregar(futuro: asyncio.Future, resultado=None, erro: Exception | None = None) -> None:
    """Resolve o pedido no laço de quem esperou (seguro mesmo vindo de outro laço)."""
    def agora():
        if not futuro.done():
            futuro.set_exception(erro) if erro else futuro.set_result(resultado)
    futuro.get_loop().call_soon_threadsafe(agora)


def _falhar_pendentes(ligacao: _Ligacao, motivo: str) -> None:
    for futuro in list(ligacao.pendentes.values()):
        _entregar(futuro, erro=PcFora(motivo))


# — No PC ——————————————————————————————————————————————————————————————————————

def deixa() -> bool:
    """O Matheus deixou o servidor usar este PC (Configurações → Servidor)."""
    return bool(banco.ajuste('servidor_usa_pc'))


def capacidades() -> dict:
    from . import pc, tela
    return {'tipo': 'ola', 'pc': platform.node() or 'PC',
            'terminal': os.name == 'nt' and os.environ.get('SOLIS_CORPO_TERMINAL', '1') != '0',
            'tela': os.name == 'nt' and tela.ligada(), 'arquivos': pc.disponivel()}


async def executar(ferramenta: str, entrada: dict) -> tuple[str, bool]:
    """O que o servidor pediu (já aprovado lá), aqui no PC, com as regras do PC."""
    from . import agente, corpo, pc, tela
    if not deixa():
        return 'O Matheus não deixou o servidor usar este PC.', False
    if ferramenta not in DE_LONGE:
        return f'O PC não faz isso pelo servidor: {ferramenta}.', False
    cap = capacidades()
    if ferramenta == TERMINAL:
        if not cap['terminal']:
            return 'O terminal está desligado neste PC.', False
        comando = str(entrada.get('command') or '').strip()
        if not comando:
            return 'Faltou o comando.', False
        saida, ok = await corpo._rodar_comando(comando, str(agente._pasta_trabalho()))
        banco.registrar_acao(None, ferramenta, entrada, ('pelo servidor: ' + saida)[:500], ok)
        return saida, ok
    if ferramenta == TELA_LER:
        if not cap['tela']:
            return 'O Controle da tela está desligado neste PC.', False
        try:
            tela.escolher_tela(entrada.get('tela'))
            return await corpo.texto_da_tela(), True
        except Exception as e:  # noqa: BLE001 — o OCR não leu: o cérebro fica sabendo
            return f'Não consegui ler a tela do PC: {e}', False
    if not cap['arquivos']:
        return 'Nenhuma pasta do PC está liberada pro Solis.', False
    # pc.rodar recusa o que está fora das pastas autorizadas e registra a ação.
    return await asyncio.to_thread(pc.rodar, ferramenta.removeprefix('mcp__solis__'), entrada, None)


def _endereco_ws() -> tuple[str, str] | None:
    s = banco.ajuste('servidor') or {}
    endereco, token = s.get('endereco') or '', cofre.abrir(s.get('token'))
    if not endereco or not token or token == cofre.ILEGIVEL:
        return None
    return endereco.replace('https://', 'wss://', 1).replace('http://', 'ws://', 1) + '/corpo', token


estado = {'ligado': False, 'erro': None}  # o que a tela do PC mostra


async def manter() -> None:
    """O laço do PC: enquanto o Matheus deixar e houver servidor, fica ligado nele;
    caiu, liga de novo (esperando mais a cada falha, até um minuto)."""
    import websockets
    espera = 2.0
    while True:
        alvo = _endereco_ws() if deixa() else None
        if alvo is None:
            estado.update(ligado=False, erro=None)
            await asyncio.sleep(10)
            continue
        url, token = alvo
        try:
            async with websockets.connect(url, additional_headers={'Authorization': f'Bearer {token}'},
                                          open_timeout=15, ping_interval=None, max_size=8 * 2**20) as ws:
                await ws.send(json.dumps(capacidades()))
                estado.update(ligado=True, erro=None)
                espera = 2.0
                log.info('corpo: ligado no servidor %s', url)
                await _servir(ws)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — rede, senha, servidor fora: tenta de novo
            erro = getattr(e, 'status_code', None) or getattr(getattr(e, 'response', None), 'status_code', None)
            estado.update(ligado=False, erro='o servidor não aceitou a senha' if erro in (401, 403) else type(e).__name__)
            log.info('corpo: sem o servidor (%s); de novo em %.0f s', estado['erro'], espera)
        await asyncio.sleep(espera)
        espera = min(60.0, espera * 2)


async def _servir(ws) -> None:
    """Atende os pedidos até a ligação cair (ou o Matheus tirar a chave)."""
    async def pulsar():
        while True:
            await asyncio.sleep(PULSO)
            if not deixa():
                await ws.close()
                return
            await ws.send(json.dumps({'tipo': 'pulso'}))

    async def atender_um(msg: dict):
        try:
            saida, ok = await executar(str(msg.get('ferramenta')), msg.get('entrada') or {})
        except Exception as e:  # noqa: BLE001 — nunca derruba a ligação
            log.exception('corpo: o pedido do servidor falhou')
            saida, ok = f'O PC não conseguiu: {e}', False
        await ws.send(json.dumps({'tipo': 'resposta', 'id': msg.get('id'), 'saida': saida, 'ok': ok}))

    batimento = asyncio.create_task(pulsar())
    tarefas: set[asyncio.Task] = set()
    try:
        async for bruto in ws:
            msg = json.loads(bruto)
            if msg.get('tipo') == 'pedido':
                t = asyncio.create_task(atender_um(msg))
                tarefas.add(t)
                t.add_done_callback(tarefas.discard)
    finally:
        batimento.cancel()
        estado['ligado'] = False
