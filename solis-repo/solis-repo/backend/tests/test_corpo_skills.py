"""As skills do Matheus pros outros cérebros (skills.do_corpo, a ferramenta Skill
do corpo): antes só o Claude seguia (PARIDADE.md). A Groq é simulada; as
skills ficam na casa de mentira dos testes (conftest)."""
import asyncio
import json

import httpx
import pytest

from solis import apis, banco, cofre, corpo, roteador, skills


@pytest.fixture
def com_skills(skills_numa_casa_de_mentira):
    """Uma da Anthropic (fica de fora), uma da conta dele, uma escrita no Solis e uma desligada."""
    base = skills_numa_casa_de_mentira / '.claude' / 'skills' / 'synced' / 'org_conta'
    base.mkdir(parents=True)
    (base / 'manifest.json').write_text(json.dumps({'skills': [
        {'name': 'docx', 'description': 'Word documents.', 'source': 'anthropic'},
        {'name': 'slides-wit', 'description': 'Gera os slides da aula do Núcleo WIT. Tema escuro, roxo.',
         'source': 'plugin'},
    ]}), encoding='utf-8')
    for nome, texto in (('docx', 'Use python-docx.'), ('slides-wit', 'Faça um .html com tema escuro e roxo lavanda.')):
        (base / nome).mkdir()
        (base / nome / 'SKILL.md').write_text(f'---\nname: {nome}\ndescription: x\n---\n{texto}\n', encoding='utf-8')
    (base / 'slides-wit' / 'modelo.html').write_text('<html></html>', encoding='utf-8')
    skills.salvar('resumo-reuniao', 'Resume uma reunião em tópicos curtos.', 'Três tópicos, no máximo.', ['claude'])
    skills.salvar('desligada', 'Não deve aparecer.', 'Nada.', ['claude'])
    skills.ligar('desligada', False)


def test_so_as_dele_e_ligadas_vao_pro_corpo(com_skills):
    nomes = [s['nome'] for s in skills.do_corpo()]
    assert nomes == ['resumo-reuniao', 'slides-wit']
    assert next(s for s in skills.do_corpo() if s['nome'] == 'slides-wit')['descricao'] == \
        'Gera os slides da aula do Núcleo WIT.'
    texto = skills.texto_pro_corpo('slides-wit')
    assert 'tema escuro e roxo lavanda' in texto and 'modelo.html' in texto
    with pytest.raises(skills.SkillInvalida):
        skills.texto_pro_corpo('docx')


def sse(*eventos):
    return '\n\n'.join([f'data: {json.dumps(e)}' for e in eventos] + ['data: [DONE]']) + '\n\n'


def resposta(*eventos):
    return httpx.Response(200, text=sse(*eventos), headers={'content-type': 'text/event-stream'})


class Gravador:
    def __init__(self):
        self.lista = []

    def marcar(self, etapa, **dados):
        self.lista.append((etapa, dados))


def test_a_groq_pede_a_skill_sem_cartao_e_segue(com_skills):
    banco.guardar_ajuste('chave:groq', cofre.selar('gsk_x'))
    banco.guardar_ajuste('modelo:groq', 'openai/gpt-oss-120b')
    vistos = []

    def rota(req):
        vistos.append(json.loads(req.content))
        if len(vistos) == 1:
            return resposta({'choices': [{'delta': {'tool_calls': [{'index': 0, 'id': 'c1', 'type': 'function',
                'function': {'name': 'Skill', 'arguments': json.dumps({'skill': 'slides-wit'})}}]}}]})
        return resposta({'choices': [{'delta': {'content': 'Segui a skill.'}}]})

    g = Gravador()
    c = corpo.Corpo(1, g, navegar=False, cerebro='groq')
    saida = asyncio.run(_juntar(apis.responder('groq', 'sis', 'faz os slides', g, httpx.MockTransport(rota), corpo=c)))
    assert saida == 'Segui a skill.'
    assert not [d for e, d in g.lista if e == 'aprovacao']
    assert [(d['ferramenta'], d['alvo'], d['ok']) for e, d in g.lista if e == 'ferramenta'] == \
        [('Skill', 'slides-wit', True)]
    devolvido = [m['content'] for m in vistos[-1]['messages'] if m.get('role') == 'tool']
    assert 'tema escuro e roxo lavanda' in devolvido[0]
    spec = next(t for t in vistos[0]['tools'] if t['function']['name'] == 'Skill')
    assert spec['function']['parameters']['properties']['skill']['enum'] == ['resumo-reuniao', 'slides-wit']


async def _juntar(fluxo):
    return ''.join([p async for p in fluxo])


def test_o_sistema_lista_as_skills_e_a_fase_leve_passa_o_pedido(com_skills):
    lista = skills.do_corpo()
    sistema = roteador.sistema_para('groq', com_o_corpo=True, skills=lista)
    assert 'chame Skill com o nome ANTES' in sistema and '- slides-wit: Gera os slides' in sistema
    leve = roteador.notas_do_cerebro('groq', [])
    assert 'resumo-reuniao, slides-wit' in leve and roteador.PASSA in leve


def test_sem_skills_nada_muda():
    assert roteador.nota_skills([]) == ''
    c = corpo.Corpo(1, navegar=False)
    assert c.lista_skills() == [] and not c.tem('Skill')
