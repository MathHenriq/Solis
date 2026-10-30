"""Importa o histórico do ChatGPT e do Claude pro Solis.

    python -m solis.importar exportacao.zip
    python -m solis.importar exportacao.zip --aprender --modelo qwen3:8b

O arquivo é o .zip que cada serviço manda por e-mail (ou o conversations.json de
dentro dele). O formato é reconhecido sozinho.

Três etapas, cada uma podendo parar e continuar depois:

1. Ler e guardar as conversas — rápido. Importar o mesmo arquivo de novo não
   duplica nada: cada conversa guarda o id que tinha no serviço de origem.
2. Vetorizar as mensagens pra busca — precisa do Ollama com o nomic-embed-text.
   Com anos de histórico, leva um tempo; o que faltar entra na próxima vez.
3. Com --aprender: tirar memórias de cada conversa, uma por uma, no modelo
   local. É a etapa lenta (uma chamada ao modelo por conversa). Ctrl+C a
   qualquer momento; rodar de novo continua de onde parou.

Formatos (lidos de exportações reais por outros projetos, não de documentação
oficial — nenhum dos dois serviços publica o esquema):
- ChatGPT: cada conversa é uma ÁRVORE (`mapping`), porque editar uma pergunta ou
  pedir outra resposta cria um galho. O que aparecia na tela é o caminho do
  `current_node` até a raiz; os galhos abandonados ficam de fora.
- Claude: cada conversa tem a lista `chat_messages`. PROVISÓRIO: os nomes dos
  campos de cada mensagem não foram confirmados — o leitor aceita as variações
  conhecidas e precisa ser conferido com um arquivo real do Matheus.
"""
import argparse
import asyncio
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import banco, busca, memoria

# Quanto das falas de uma conversa vai pra extração de memória. Conversa enorme
# passaria da janela do modelo; o começo é onde costuma estar o contexto.
FALAS_MAX = 6000


def ler_arquivo(caminho: Path) -> list[dict]:
    """A lista de conversas, do .zip ou do .json direto."""
    if caminho.suffix.lower() == '.zip':
        with zipfile.ZipFile(caminho) as z:
            nome = next((n for n in z.namelist() if n.rsplit('/', 1)[-1] == 'conversations.json'), None)
            if nome is None:
                raise ValueError('o .zip não tem um conversations.json')
            return json.loads(z.read(nome))
    return json.loads(caminho.read_text(encoding='utf-8'))


def formato(conversas: list[dict]) -> str:
    amostra = next((c for c in conversas if isinstance(c, dict)), {})
    if 'mapping' in amostra:
        return 'chatgpt'
    if 'chat_messages' in amostra:
        return 'claude'
    raise ValueError('formato não reconhecido: nem ChatGPT (mapping) nem Claude (chat_messages)')


def _iso(valor) -> str | None:
    """Epoch (ChatGPT) ou ISO (Claude) → ISO em UTC, como o resto do banco."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return datetime.fromtimestamp(valor, timezone.utc).isoformat(timespec='seconds')
    try:
        return datetime.fromisoformat(str(valor).replace('Z', '+00:00')).astimezone(timezone.utc).isoformat(
            timespec='seconds'
        )
    except ValueError:
        return None


PAPEIS = {'user': 'pessoa', 'human': 'pessoa', 'assistant': 'solis'}


def mensagens_chatgpt(conversa: dict) -> list[dict]:
    mapa = conversa.get('mapping') or {}
    no, caminho, visto = conversa.get('current_node'), [], set()
    # Do fim até a raiz, pelo pai. O `visto` protege de arquivo com ciclo.
    while no and no in mapa and no not in visto:
        visto.add(no)
        caminho.append(mapa[no])
        no = mapa[no].get('parent')
    saida = []
    for item in reversed(caminho):
        msg = item.get('message') or {}
        papel = PAPEIS.get((msg.get('author') or {}).get('role'))
        conteudo = msg.get('content') or {}
        # Só texto: código executado, imagem e saída de ferramenta ficam de fora.
        if papel is None or conteudo.get('content_type') not in ('text', 'multimodal_text'):
            continue
        texto = '\n'.join(p for p in conteudo.get('parts') or [] if isinstance(p, str)).strip()
        if texto:
            saida.append({'papel': papel, 'texto': texto, 'criada': _iso(msg.get('create_time'))})
    return saida


def mensagens_claude(conversa: dict) -> list[dict]:
    saida = []
    for msg in conversa.get('chat_messages') or []:
        papel = PAPEIS.get(msg.get('sender') or msg.get('role'))
        texto = msg.get('text') or ''
        if not texto and isinstance(msg.get('content'), list):
            texto = '\n'.join(b.get('text', '') for b in msg['content'] if isinstance(b, dict) and b.get('type') == 'text')
        if papel and texto.strip():
            saida.append({'papel': papel, 'texto': texto.strip(), 'criada': _iso(msg.get('created_at'))})
    return saida


LEITORES = {
    'chatgpt': (mensagens_chatgpt, lambda c: c.get('id') or c.get('conversation_id'), 'title', 'create_time'),
    'claude': (mensagens_claude, lambda c: c.get('uuid'), 'name', 'created_at'),
}


def guardar(conversas: list[dict], origem: str) -> dict:
    """Etapa 1. Devolve quantas conversas e mensagens entraram e quantas já existiam."""
    ler_mensagens, ler_id, campo_titulo, campo_data = LEITORES[origem]
    novas = repetidas = vazias = mensagens = 0
    for c in conversas:
        externo = f'{origem}:{ler_id(c)}'
        if banco.conversa_externa(externo):
            repetidas += 1
            continue
        lista = ler_mensagens(c)
        if not lista:
            vazias += 1
            continue
        criada = _iso(c.get(campo_data)) or lista[0]['criada']
        cid = banco.nova_conversa(origem=origem, titulo=c.get(campo_titulo), externo=externo, criada=criada)
        for m in lista:
            banco.adicionar(
                cid, m['papel'], m['texto'],
                # Dito em sigilo lá também é sigilo aqui.
                privada=m['papel'] == 'pessoa' and memoria.eh_privado(m['texto']),
                criada=m['criada'] or criada,
            )
        novas += 1
        mensagens += len(lista)
    return {'novas': novas, 'repetidas': repetidas, 'vazias': vazias, 'mensagens': mensagens}


async def aprender_importadas(modelo: str, aviso=print) -> int:
    """Etapa 3. Uma chamada ao modelo local por conversa ainda não aprendida."""
    pendentes = banco.importadas_por_aprender()
    for i, c in enumerate(pendentes, 1):
        falas = '\n\n'.join(m['texto'] for m in banco.mensagens(c['id']) if m['papel'] == 'pessoa')
        if falas.strip():
            quando = (c['criada'] or '')[:10]
            antiga = f'{"ChatGPT" if c["origem"] == "chatgpt" else "Claude"}, {quando}'
            await memoria.aprender(modelo, c['id'], falas[:FALAS_MAX], [], antiga=antiga)
        banco.marcar_aprendida(c['id'])
        aviso(f'  memórias: {i}/{len(pendentes)} — {c["titulo"] or "(sem título)"}')
    return len(pendentes)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog='python -m solis.importar', description='Importa o histórico do ChatGPT ou do Claude.')
    p.add_argument('arquivo', type=Path, help='o .zip da exportação, ou o conversations.json')
    p.add_argument('--aprender', action='store_true', help='tirar memórias das conversas importadas (lento)')
    p.add_argument('--modelo', help='modelo local pra --aprender, ex.: qwen3:8b')
    args = p.parse_args(argv)
    if args.aprender and not args.modelo:
        p.error('--aprender precisa de --modelo')

    conversas = ler_arquivo(args.arquivo)
    origem = formato(conversas)
    r = guardar(conversas, origem)
    print(f'{origem}: {r["novas"]} conversas novas ({r["mensagens"]} mensagens), '
          f'{r["repetidas"]} já importadas, {r["vazias"]} vazias.')

    print('Vetorizando pra busca (precisa do Ollama)...')
    n = asyncio.run(busca.indexar_pendentes())
    sobra = len(banco.sem_vetor('mensagem', 1))
    print(f'  {n} vetorizadas.' + (' Faltou parte: o Ollama ou o nomic-embed-text não respondeu; rode de novo depois.' if sobra else ''))

    if args.aprender:
        print(f'Tirando memórias com {args.modelo} (Ctrl+C pra parar; rodar de novo continua)...')
        asyncio.run(aprender_importadas(args.modelo))
        asyncio.run(busca.indexar_pendentes())


if __name__ == '__main__':
    main()
