"""O plano do Claude (a lista de tarefas que ele mostra fazendo): TaskCreate e
TaskUpdate viram a etapa `plano`, não passos."""
import asyncio

import pytest

pytest.importorskip('claude_agent_sdk')

from claude_agent_sdk import AssistantMessage, ToolResultBlock, ToolUseBlock, UserMessage  # noqa: E402

from solis import agente  # noqa: E402


def _rodar(viva, mensagens):
    mandados = []

    async def ir():
        viva.resposta = agente._Resposta(viva, lambda t, v=None: mandados.append((t, v)), {}, 'pedir')
        for m in mensagens:
            viva.resposta.receber(m)
    asyncio.run(ir())
    return mandados


def _uso(id_, nome, entrada):
    return AssistantMessage(content=[ToolUseBlock(id=id_, name=nome, input=entrada)], model='m')


def _res(id_, resultado=None):
    return UserMessage(content=[ToolResultBlock(tool_use_id=id_, content='ok', is_error=False)],
                       tool_use_result=resultado)


def test_plano_criado_e_marcado():
    viva = agente._Viva(None, None, None, 'pedir')
    mandados = _rodar(viva, [
        _uso('t1', 'TaskCreate', {'subject': 'Criar a.txt'}), _res('t1', {'task': {'id': '1', 'subject': 'Criar a.txt'}}),
        _uso('t2', 'TaskCreate', {'subject': 'Criar b.txt'}), _res('t2', {'task': {'id': '2', 'subject': 'Criar b.txt'}}),
        _uso('u1', 'TaskUpdate', {'taskId': '1', 'status': 'in_progress'}), _res('u1'),
        _uso('u2', 'TaskUpdate', {'taskId': '1', 'status': 'completed'}), _res('u2'),
        _uso('u3', 'TaskUpdate', {'taskId': '1', 'status': 'completed'}), _res('u3'),  # repetido: não muda
    ])
    planos = [v[1]['itens'] for t, v in mandados if t == 'etapa' and v[0] == 'plano']
    assert len(planos) == 4  # 2 criadas, fazendo, feita (o repetido não manda)
    assert planos[-1] == [{'id': '1', 'texto': 'Criar a.txt', 'estado': 'feita'},
                          {'id': '2', 'texto': 'Criar b.txt', 'estado': 'pendente'}]
    # As ferramentas do plano não viram passo.
    assert not any(t == 'etapa' and v[0] == 'ferramenta' for t, v in mandados)


def test_plano_continua_na_sessao_e_apaga():
    viva = agente._Viva(None, None, None, 'pedir')
    _rodar(viva, [_uso('t1', 'TaskCreate', {'subject': 'A'}), _res('t1', {'task': {'id': '1', 'subject': 'A'}})])
    mandados = _rodar(viva, [_uso('u1', 'TaskUpdate', {'taskId': '1', 'status': 'deleted'}), _res('u1')])
    assert viva.plano == [] and mandados[-1] == ('etapa', ('plano', {'itens': []}))


def test_todowrite_antigo():
    viva = agente._Viva(None, None, None, 'pedir')
    assert viva.mudar_plano('TodoWrite', {'todos': [{'content': 'X', 'status': 'in_progress'},
                                                     {'content': 'Y', 'status': 'pending'}]}, None)
    assert [i['estado'] for i in viva.plano] == ['fazendo', 'pendente']


def test_as_ferramentas_do_plano_sao_livres():
    r = asyncio.run(agente._decidir('TaskCreate', {'subject': 'x'}, lambda *a: None))
    assert r.behavior == 'allow'
