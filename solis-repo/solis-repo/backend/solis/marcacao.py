"""A chamada de ferramenta escrita como texto, que vaza na resposta.

Um modelo às vezes escreve a chamada de ferramenta no texto em vez de chamar de
verdade: <function_calls>, <invoke name="...">, <parameter name="...">, com ou
sem o prefixo antml:. Visto em 26/11/2026 com o Claude pelo Agent SDK (cérebro
claude, "Quanto é 7 vezes 8?"): a primeira tentativa dele saiu com a chamada
malformada, o CLI descartou e pediu de novo ("The previous response failed to
produce a valid tool call. Please retry the tool call now." na transcrição da
sessão), mas os pedaços da tentativa descartada já tinham ido pelo stream. A
resposta guardada e mostrada foi 'antml:invoke name="mcp__solis__hora">\\n</invoke>7 × 8 = 56.'
— repare: abre sem o "<" e fecha sem o prefixo. As formas se misturam.

Aqui a marca sai do texto pedaço a pedaço: o que pode ser o começo de uma marca
fica esperando o próximo pedaço (ela chega partida), o resto segue na hora. A
marca sai inteira, com o que estiver dentro (os parâmetros). O que está dentro
de código (```...``` ou `...`) fica como veio: ali a marca pode ser o assunto
(um exemplo, um XML de BPEL com <invoke name=...>).

Vale pra qualquer cérebro (as funções são do Solis): cerebros.abrir passa todos
por aqui, o local passa no roteador, e o agente.py limpa cada mensagem do
Claude (a tentativa descartada termina ali, mesmo com a marca aberta).
"""
import functools
import re
from collections.abc import AsyncIterator

# As marcas: as de chamar ferramenta e a de resultado (um resultado inventado
# no texto é lorota do mesmo jeito).
_NOMES = r'(?P<nome>function_calls|function_results|invoke|parameter)'
_ATTRS_MAX = 500
# Com o "<": <invoke name="x">, </invoke>, <function_calls>...
_TAG = re.compile(r'<(?P<fecha>/)?(?P<prefixo>antml:)?' + _NOMES + rf'(?=[\s/>])(?P<atributos>[^>]{{0,{_ATTRS_MAX}}})>')
# Sem o "<", só com o prefixo (como no caso de 26/11): antml:invoke name="x">.
_NUA = re.compile(r'(?P<fecha>/)?(?P<prefixo>antml:)' + _NOMES + rf'(?=[\s/>])(?P<atributos>[^>]{{0,{_ATTRS_MAX}}})>')
# Onde algo pode começar: código (crase, til) ou uma marca.
_ESPECIAL = re.compile(r'[`~<]|(?<![\w<])/?antml:')
_CORRIDA = re.compile(r'`+|~+')
_CRASE_OU_LINHA = re.compile(r'`+|\n')
_CABECAS = tuple(
    abre + prefixo + nome
    for nome in ('function_calls', 'function_results', 'invoke', 'parameter')
    for prefixo in ('', 'antml:')
    for abre in ('<', '</')
) + tuple(barra + 'antml:' + nome for nome in ('function_calls', 'function_results', 'invoke', 'parameter')
          for barra in ('', '/'))
_PREFIXOS_NUS = ('antml:', '/antml:')
# Dentro de uma marca aberta, o fim do pedaço pode ser o começo do fechamento.
_SEGURA_FECHO = 40


@functools.cache
def _fecho(nome: str) -> re.Pattern:
    return re.compile(rf'</(?:antml:)?{nome}\s*>|(?<![\w<])/antml:{nome}\s*>')


def _eh_marca(m: re.Match) -> bool:
    """Uma tag que casou é marca de chamada? Sem o prefixo, <invoke> e
    <parameter> só com o name= (é sempre assim na chamada; sem ele, pode ser
    outra coisa)."""
    if m['prefixo'] or m['fecha'] or m['nome'] in ('function_calls', 'function_results'):
        return True
    return 'name=' in m['atributos']


def _cabeca(s: str) -> tuple[str, str] | None:
    """('parcial', cabeça): `s` é o começo de uma cabeça de marca (<inv, </function_c,
    antml:par); ('inteira', cabeça): começa com a cabeça inteira e o limite (espaço,
    / ou >), mas o ">" ainda não veio; None: não é marca."""
    for c in _CABECAS:
        if len(s) < len(c) and c.startswith(s):
            return 'parcial', c
        if s.startswith(c) and (len(s) == len(c) or s[len(c)] in ' \t\r\n/>'):
            return 'inteira', c
    return None


class Filtro:
    """Tira a marca de um texto que chega aos pedaços. `passar(pedaco)` devolve
    o que já pode sair; `fechar()` devolve o que sobrou no fim (e deixa o filtro
    pronto pra um texto novo, como a próxima mensagem do Claude)."""

    def __init__(self):
        self.buf = ''
        self.estado = 'texto'  # texto | bloco (uma marca aberta, saindo) | cerca (```) | crase (`...`)
        self.abertura = ''     # bloco: o nome da marca; cerca e crase: a corrida que abriu
        self.pular = False     # depois de tirar uma marca: o espaço que sobraria no lugar dela
        self.anterior = ''     # o último caractere que saiu
        self.coluna: int | None = 0  # espaços desde a quebra de linha (None: a linha já tem texto)
        self.tiradas = 0

    def passar(self, pedaco: str) -> str:
        self.buf += pedaco
        return self._andar(final=False)

    def fechar(self) -> str:
        saida = self._andar(final=True)
        self.buf, self.estado, self.abertura, self.pular = '', 'texto', '', False
        return saida

    # — por dentro ——————————————————————————————————————————————————————————————
    def _saiu(self, seg: str) -> None:
        self.anterior = seg[-1]
        if '\n' in seg:
            seg, self.coluna = seg.rsplit('\n', 1)[1], 0
        if self.coluna is not None:
            n = self.coluna + len(seg)
            self.coluna = n if n <= 3 and not seg.strip(' ') else None

    def _tirou(self) -> None:
        """Uma marca saiu: o espaço logo depois dela também, se ela estava no
        começo da resposta ou de uma linha (senão sobraria linha em branco)."""
        self.pular = not self.anterior or self.anterior == '\n'

    def _andar(self, final: bool) -> str:
        buf, pos, saida = self.buf, 0, []

        def sair(ate: int) -> None:
            nonlocal pos
            if ate > pos:
                seg = buf[pos:ate]
                saida.append(seg)
                self._saiu(seg)
            pos = ate

        while pos < len(buf):
            if self.estado == 'bloco':
                m = _fecho(self.abertura).search(buf, pos)
                if m is None:
                    # Tudo aqui dentro é marca: sai fora. Só o fim espera (pode ser o fechamento partido).
                    pos = len(buf) if final else max(pos, len(buf) - _SEGURA_FECHO)
                    break
                pos = m.end()
                self.estado, self.abertura = 'texto', ''
                self._tirou()
                continue

            if self.estado == 'cerca':
                fim_da_linha = buf.find('\n', pos)
                if self.coluna is None:  # no meio de uma linha de código: até o fim dela
                    if fim_da_linha == -1:
                        sair(len(buf))
                        break
                    sair(fim_da_linha + 1)
                    continue
                # No começo de uma linha: ela pode fechar a cerca.
                c, n = self.abertura[0], len(self.abertura)
                linha = ' ' * self.coluna + (buf[pos:] if fim_da_linha == -1 else buf[pos:fim_da_linha])
                if fim_da_linha == -1:
                    if not final and re.fullmatch(rf' {{0,3}}{re.escape(c)}*[ \t]*', linha):
                        break  # pode ser o fechamento chegando
                    sair(len(buf))
                    break
                if re.fullmatch(rf' {{0,3}}{re.escape(c)}{{{n},}}[ \t]*\r?', linha):
                    self.estado, self.abertura = 'texto', ''
                sair(fim_da_linha + 1)
                continue

            if self.estado == 'crase':
                m = _CRASE_OU_LINHA.search(buf, pos)
                if m is None:
                    sair(len(buf))
                    break
                if m.group() == '\n':
                    # A crase ficou sozinha na linha: não era código.
                    self.estado, self.abertura = 'texto', ''
                    sair(m.start())
                    continue
                if m.end() == len(buf) and not final:
                    sair(m.start())
                    break  # a corrida de crases pode crescer
                if len(m.group()) == len(self.abertura):
                    self.estado, self.abertura = 'texto', ''
                sair(m.end())
                continue

            # — texto ——————————————————————————————————————————————————————————————
            if self.pular:
                j = pos
                while j < len(buf) and buf[j] in ' \t\r\n':
                    j += 1
                pos = j
                if j == len(buf):
                    break
                self.pular = False
            m = _ESPECIAL.search(buf, pos)
            if m is None:
                sair(len(buf) if final else len(buf) - self._prefixo_nu_no_fim(buf, pos))
                break
            i = m.start()
            sair(i)
            if buf[i] in '`~':
                corrida = _CORRIDA.match(buf, i)
                if corrida.end() == len(buf) and not final:
                    break  # ``` partido: espera
                abertura = corrida.group()
                if len(abertura) >= 3 and self.coluna is not None:
                    self.estado, self.abertura = 'cerca', abertura
                elif abertura[0] == '`':
                    self.estado, self.abertura = 'crase', abertura
                sair(corrida.end())
                continue
            marca = self._marca(buf, i, final)
            if marca is None:
                break  # pode ser uma marca chegando: espera o próximo pedaço
            if marca is False:
                sair(i + 1)
                continue
            if marca == 'resto':
                pos = len(buf)  # uma marca que nunca fechou, no fim
                break
            pos = marca.end()
            self.tiradas += 1
            if not marca['fecha'] and not marca['atributos'].rstrip().endswith('/'):
                self.estado, self.abertura = 'bloco', marca['nome']
            else:
                self._tirou()
        self.buf = buf[pos:]
        return ''.join(saida)

    def _marca(self, buf: str, i: int, final: bool):
        """Em `i` há uma marca? O match dela; False (não é); None (ainda não dá
        pra saber); 'resto' (no fim, uma marca que nunca fechou o ">")."""
        nua = buf[i] != '<'
        if nua:
            antes = buf[i - 1] if i > 0 else self.anterior
            if antes and (antes.isalnum() or antes in '_<'):
                return False
        m = (_NUA if nua else _TAG).match(buf, i)
        if m:
            return m if _eh_marca(m) else False
        s = buf[i:]
        achada = _cabeca(s)
        if achada is None:
            return False
        if not final:
            # Esperando o ">" (ou o resto do nome), até o limite de uma marca.
            return None if len(s) <= _ATTRS_MAX + 30 and '>' not in s else False
        # No fim, sem o ">": a cabeça inteira de uma marca é marca (a mesma regra
        # do _eh_marca); o começo de uma (um "<inv" solto) fica como texto.
        tipo, cabeca = achada
        if tipo == 'inteira' and ('antml:' in cabeca or cabeca.startswith('</') or 'function_' in cabeca
                                  or 'name=' in s):
            self.tiradas += 1
            return 'resto'
        return False

    def _prefixo_nu_no_fim(self, buf: str, pos: int) -> int:
        """Quantos caracteres do fim podem ser o começo de "antml:" (sem o "<")."""
        for k in range(min(len('/antml:') - 1, len(buf) - pos), 0, -1):
            fim = buf[-k:]
            if any(p.startswith(fim) for p in _PREFIXOS_NUS):
                antes = buf[-k - 1] if len(buf) - k - 1 >= 0 else self.anterior
                if not antes or not (antes.isalnum() or antes in '_<'):
                    return k
        return 0


def limpar(texto: str) -> str:
    """O texto inteiro de uma vez, sem a marca."""
    f = Filtro()
    return f.passar(texto) + f.fechar()


async def sem_marcacao(fluxo: AsyncIterator[str]) -> AsyncIterator[str]:
    """O fluxo de uma resposta, sem a marca. Pedaço que fica vazio não sai
    (quem espera a primeira palavra espera a de verdade)."""
    f = Filtro()
    try:
        async for pedaco in fluxo:
            limpo = f.passar(pedaco)
            if limpo:
                yield limpo
    except Exception:
        # Caiu no meio: o que já chegou e estava esperando sai antes do erro.
        if resto := f.fechar():
            yield resto
        raise
    else:
        if resto := f.fechar():
            yield resto
    finally:
        fechar = getattr(fluxo, 'aclose', None)
        if fechar is not None:
            await fechar()
