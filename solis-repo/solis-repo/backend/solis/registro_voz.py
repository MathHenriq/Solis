"""O registro de cada chamada pela voz (22/11/2026): "um dia de uso real, com o
registro de cada chamada" (a ordem do painel, docs/progresso.html). Uma linha por
acontecimento, ao lado do banco (nos testes, no temporário deles — nunca nos dados
do Matheus):

- acordou: quem ouviu o "Solis" (o Whisper, o motor, ou a resposta a uma
  pergunta), se o detector treinado também ouviu (o modo sombra) e quanto a
  decisão levou;
- sombra: o detector treinado acordaria (pra contar os alarmes falsos dele);
- pedido: o caminho (ao_vivo, texto, privado, passou, falhou, conversa, nada),
  quanto o texto levou depois do fim da fala, e, ao vivo, o primeiro som e as
  ferramentas usadas.

Só números e o caminho — nunca o que foi dito (o texto fica na conversa, onde o
privado já é tratado). `resumo` junta um período: é o que mede o "pronto quando"
da voz (chamar 19 de 20, 0 falsos em 1 h, primeiro som)."""
from __future__ import annotations

import json
import logging
import statistics
import threading
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from . import banco

log = logging.getLogger('solis.registro_voz')
_trava = threading.Lock()
# Um disparo do detector com uma chamada até este tanto depois é a mesma chamada.
JUNTO_S = 5


def arquivo() -> Path:
    return banco.arquivo().parent / 'voz-chamadas.jsonl'


def anotar(evento: str, **dados) -> None:
    linha = {'quando': datetime.now().isoformat(timespec='seconds'), 'evento': evento,
             **{k: v for k, v in dados.items() if v is not None}}
    try:
        with _trava, arquivo().open('a', encoding='utf-8') as f:
            f.write(json.dumps(linha, ensure_ascii=False) + '\n')
    except OSError:
        log.warning('registro da voz: não consegui anotar', exc_info=True)


def ler(horas: float = 24) -> list[dict]:
    desde = datetime.now() - timedelta(hours=horas)
    try:
        linhas = arquivo().read_text(encoding='utf-8').splitlines()
    except OSError:
        return []
    eventos = []
    for linha in linhas:
        try:
            e = json.loads(linha)
            if datetime.fromisoformat(e['quando']) >= desde:
                eventos.append(e)
        except (ValueError, KeyError, TypeError):
            continue
    return eventos


def _mediana(valores: list[float]) -> float | None:
    return round(statistics.median(valores), 2) if valores else None


def resumo(horas: float = 24) -> dict:
    eventos = ler(horas)
    acordou = [e for e in eventos if e['evento'] == 'acordou']
    pedidos = [e for e in eventos if e['evento'] == 'pedido']
    sombras = [e for e in eventos if e['evento'] == 'sombra']
    momentos = [datetime.fromisoformat(e['quando']) for e in acordou]
    # O disparo do detector sem chamada do Whisper perto: um possível alarme falso dele.
    sozinhos = [s for s in sombras if not any(
        abs((m - datetime.fromisoformat(s['quando'])).total_seconds()) <= JUNTO_S for m in momentos)]
    pelo_whisper = [e for e in acordou if e.get('por') == 'whisper']
    com_sombra = [e for e in pelo_whisper if 'sombra' in e]
    ao_vivo = [e for e in pedidos if e.get('caminho') == 'ao_vivo']
    return {
        'horas': horas,
        'chamadas': len(acordou),
        'por': dict(Counter(e.get('por', '?') for e in acordou)),
        'decisao_s': _mediana([e['decisao_s'] for e in acordou if 'decisao_s' in e]),
        'detector_tambem_ouviu': f'{sum(e["sombra"] for e in com_sombra)} de {len(com_sombra)}' if com_sombra else None,
        'detector_disparos_sem_chamada': len(sozinhos),
        'pedidos': len(pedidos),
        'caminhos': dict(Counter(e.get('caminho', '?') for e in pedidos)),
        'texto_s': _mediana([e['texto_s'] for e in pedidos if 'texto_s' in e]),
        'ao_vivo_primeiro_som_s': _mediana([e['primeiro_som_s'] for e in ao_vivo if 'primeiro_som_s' in e]),
        'ao_vivo_pior_s': max((e['primeiro_som_s'] for e in ao_vivo if 'primeiro_som_s' in e), default=None),
        'falhas': dict(Counter(e.get('motivo', '?') for e in pedidos if e.get('caminho') == 'falhou')),
    }


def motivo_da_falha(texto: str) -> str:
    """A categoria da falha do Gemini, sem a mensagem dele."""
    t = texto.lower()
    if any(x in t for x in ('429', 'quota', 'resource_exhausted')):
        return 'limite'
    if 'não abriu' in t or 'nao abriu' in t:
        return 'nao_abriu'
    if 'a tempo' in t or 'timeout' in t:
        return 'demorou'
    if 'chave' in t or '403' in t or '401' in t:
        return 'chave'
    return 'erro'


def agora() -> float:
    return time.monotonic()
