"""Estilos de resposta (docs/PARIDADE.md): como o cérebro escreve — Normal,
Conciso, Explicativo, Formal, ou um estilo do Matheus —, como os estilos do
claude.ai. Vale pra toda resposta, de qualquer cérebro, até ele trocar: vai
como uma nota no fim da mensagem pro cérebro (como a da pesquisa), e o que
fica guardado na conversa é só o que ele escreveu."""
from __future__ import annotations

import uuid

from . import banco

PRONTOS = {
    'normal': ('Normal', ''),
    'conciso': ('Conciso', 'Responda curto e direto: só o essencial, sem introdução nem resumo no fim. Se der pra '
                'dizer em uma frase, diga em uma.'),
    'explicativo': ('Explicativo', 'Explique com calma, como um bom professor: o porquê das coisas, passo a passo, '
                    'com um exemplo quando ajudar a entender.'),
    'formal': ('Formal', 'Escreva em tom formal e profissional: frases completas, vocabulário cuidado, sem gírias '
               'nem brincadeiras.'),
}
NOME_MAX = 40
INSTRUCOES_MAX = 2000


class EstiloInvalido(Exception):
    pass


def _seus() -> list[dict]:
    return list(banco.ajuste('estilos_seus') or [])


def listar() -> dict:
    """{'atual': id, 'estilos': [{id, nome, instrucoes, seu}]}: os prontos e os dele."""
    estilos = [{'id': i, 'nome': n, 'instrucoes': t, 'seu': False} for i, (n, t) in PRONTOS.items()]
    estilos += [{**e, 'seu': True} for e in _seus()]
    return {'atual': atual()['id'], 'estilos': estilos}


def atual() -> dict:
    escolhido = banco.ajuste('estilo') or 'normal'
    return next((e for e in listar_todos() if e['id'] == escolhido), listar_todos()[0])


def listar_todos() -> list[dict]:
    return [{'id': i, 'nome': n, 'instrucoes': t} for i, (n, t) in PRONTOS.items()] + _seus()


def escolher(id_: str) -> dict:
    if id_ not in {e['id'] for e in listar_todos()}:
        raise EstiloInvalido('estilo')
    banco.guardar_ajuste('estilo', id_)
    return listar()


def _validar(nome: str, instrucoes: str) -> None:
    if not nome.strip() or len(nome) > NOME_MAX:
        raise EstiloInvalido('nome')
    if not instrucoes.strip() or len(instrucoes) > INSTRUCOES_MAX:
        raise EstiloInvalido('instruções')


def salvar(nome: str, instrucoes: str, id_: str | None = None) -> dict:
    """Cria (sem `id_`) ou muda um estilo dele."""
    nome, instrucoes = ' '.join(nome.split()), instrucoes.strip()
    _validar(nome, instrucoes)
    seus = _seus()
    outros = [e for e in listar_todos() if e['id'] != id_]
    if nome.lower() in {e['nome'].lower() for e in outros}:
        raise EstiloInvalido('já existe um estilo com esse nome')
    if id_:
        if not any(e['id'] == id_ for e in seus):
            raise EstiloInvalido('esse estilo não existe mais')
        seus = [{**e, 'nome': nome, 'instrucoes': instrucoes} if e['id'] == id_ else e for e in seus]
        novo = id_
    else:
        novo = f'seu-{uuid.uuid4().hex[:8]}'
        seus.append({'id': novo, 'nome': nome, 'instrucoes': instrucoes})
    banco.guardar_ajuste('estilos_seus', seus)
    return next({**e, 'seu': True} for e in seus if e['id'] == novo)


def apagar(id_: str) -> bool:
    seus = _seus()
    if not any(e['id'] == id_ for e in seus):
        return False
    banco.guardar_ajuste('estilos_seus', [e for e in seus if e['id'] != id_])
    if banco.ajuste('estilo') == id_:
        banco.guardar_ajuste('estilo', 'normal')
    return True


def nota() -> str:
    """A nota pro cérebro, no fim da mensagem (vazia no Normal)."""
    e = atual()
    if not e['instrucoes']:
        return ''
    return f'\n\n[Estilo de resposta escolhido pelo Matheus: {e["nome"]}. {e["instrucoes"]}]'
