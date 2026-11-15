"""Skills (docs/PARIDADE.md): as da conta do claude.ai (só ler e ligar/desligar)
e as escritas no Solis, cada uma pra quem serve — Claude, Codex ou os dois."""
import json

import pytest
from fastapi.testclient import TestClient

from solis import banco, main, skills


@pytest.fixture
def conta(skills_numa_casa_de_mentira):
    """O que o CLI do Claude sincroniza da conta do claude.ai."""
    base = skills_numa_casa_de_mentira / '.claude' / 'skills' / 'synced' / 'org_conta'
    base.mkdir(parents=True)
    (base / 'manifest.json').write_text(json.dumps({'skills': [
        {'name': 'docx', 'description': 'Word documents', 'source': 'anthropic'},
        {'name': 'plano-de-aula-wit', 'description': 'Plano de aula\n  do Núcleo', 'source': 'plugin'},
    ]}), encoding='utf-8')
    return base


def test_nome_de():
    assert skills.nome_de('Resumo de Reunião!') == 'resumo-de-reuniao'
    assert skills.nome_de('  ---  ') == ''


def test_lista_a_conta_e_as_suas(conta, skills_numa_casa_de_mentira):
    mao = skills_numa_casa_de_mentira / '.codex' / 'skills' / 'revisar-pr'
    mao.mkdir(parents=True)
    (mao / 'SKILL.md').write_text('---\nname: "revisar-pr"\ndescription: >\n  Revisa um PR\n  com calma\n---\n\nPasso 1',
                                  encoding='utf-8')
    sistema = skills_numa_casa_de_mentira / '.codex' / 'skills' / '.system' / 'imagegen'
    sistema.mkdir(parents=True)
    (sistema / 'SKILL.md').write_text('---\nname: imagegen\ndescription: x\n---\n', encoding='utf-8')
    lista = skills.listar()
    assert [(s['nome'], s['origem'], s['para']) for s in lista] == [
        ('revisar-pr', 'solis', ['codex']), ('plano-de-aula-wit', 'conta', ['claude']),
        ('docx', 'anthropic', ['claude'])]
    assert lista[0]['descricao'] == 'Revisa um PR com calma' and lista[0]['editavel']
    assert lista[1]['descricao'] == 'Plano de aula do Núcleo' and not lista[1]['editavel']
    assert all(s['ligada'] for s in lista)


def test_escrever_pra_um_e_pros_dois(skills_numa_casa_de_mentira):
    s = skills.salvar('resumo-de-reuniao', 'Use quando pedirem resumo de reunião.', 'Faça em tópicos.', ['claude'])
    claude_md = skills.pasta('claude') / 'resumo-de-reuniao' / 'SKILL.md'
    assert s['para'] == ['claude'] and claude_md.is_file()
    cabecalho, corpo = skills.ler_skill_md(claude_md)
    assert cabecalho == {'name': 'resumo-de-reuniao', 'description': 'Use quando pedirem resumo de reunião.'}
    assert corpo.strip() == 'Faça em tópicos.'
    assert not (skills.pasta('codex') / 'resumo-de-reuniao').exists()
    # Um script de apoio na pasta vai junto quando passa a valer pros dois.
    (claude_md.parent / 'apoio.py').write_text('print(1)')
    skills.salvar('resumo-de-reuniao', 'Resumo de reunião.', 'Em tópicos curtos.', ['claude', 'codex'],
                  antigo='resumo-de-reuniao')
    assert (skills.pasta('codex') / 'resumo-de-reuniao' / 'apoio.py').is_file()
    assert skills.ler('resumo-de-reuniao') == {'nome': 'resumo-de-reuniao', 'descricao': 'Resumo de reunião.',
                                               'instrucoes': 'Em tópicos curtos.', 'para': ['claude', 'codex']}
    # Só pro Codex: sai do Claude (pra lixeira, não some), e renomear leva a pasta.
    skills.salvar('resumo', 'Resumo.', 'Curto.', ['codex'], antigo='resumo-de-reuniao')
    assert not (skills.pasta('claude') / 'resumo-de-reuniao').exists()
    assert (skills.pasta('codex') / 'resumo' / 'apoio.py').is_file()
    assert any(p.name.startswith('resumo-de-reuniao-claude-') for p in skills.lixeira().iterdir())


@pytest.mark.parametrize('nome, descricao, instrucoes, para, motivo', [
    ('Com Espaço', 'd', 'i', ['claude'], 'nome'),
    ('synced', 'd', 'i', ['claude'], 'nome'),
    ('ok', ' ', 'i', ['claude'], 'descrição'),
    ('ok', 'd', '', ['claude'], 'instruções'),
    ('ok', 'd', 'i', [], 'pra quem'),
    ('ok', 'd', 'i', ['gemini'], 'pra quem'),
])
def test_recusa(nome, descricao, instrucoes, para, motivo):
    with pytest.raises(skills.SkillInvalida, match=motivo):
        skills.salvar(nome, descricao, instrucoes, para)


def test_nao_sobrescreve(conta):
    skills.salvar('minha', 'd', 'i', ['claude'])
    with pytest.raises(skills.SkillInvalida, match='já existe'):
        skills.salvar('minha', 'd', 'i', ['codex'])
    with pytest.raises(skills.SkillInvalida, match='da sua conta'):
        skills.salvar('docx', 'd', 'i', ['claude'])


def test_apagar_vai_pra_lixeira():
    skills.salvar('velha', 'd', 'i', ['claude', 'codex'])
    assert skills.apagar('velha')
    assert skills.ler('velha') is None and len(list(skills.lixeira().iterdir())) == 2
    assert not skills.apagar('velha')


def test_desligar_filtra_o_claude(conta):
    assert skills.filtro() == 'all'
    skills.lembrar_descobertas(['claude-api', 'anthropic-skills:docx', 'anthropic-skills:plano-de-aula-wit'])
    skills.salvar('minha', 'd', 'i', ['claude'])
    skills.ligar('docx', False)
    # Sem docx nem anthropic-skills:docx (o nome que o CLI dá às da conta).
    assert skills.filtro() == ['anthropic-skills:plano-de-aula-wit', 'claude-api', 'minha', 'plano-de-aula-wit']
    assert next(s for s in skills.listar() if s['nome'] == 'docx')['ligada'] is False
    skills.ligar('docx', True)
    assert skills.filtro() == 'all'


def test_rotas(conta):
    cli = TestClient(main.app)
    r = cli.post('/skills', json={'nome': 'minha', 'descricao': 'Quando pedir X.', 'instrucoes': 'Faça Y.',
                                  'para': ['claude', 'codex']})
    assert r.json()['para'] == ['claude', 'codex']
    assert cli.get('/skills/minha').json()['instrucoes'] == 'Faça Y.'
    assert cli.get('/skills/nada').status_code == 404
    r = cli.post('/skills', json={'nome': 'Minha Skill', 'descricao': 'd', 'instrucoes': 'i', 'para': ['claude']})
    assert r.status_code == 400 and r.json()['motivo'] == 'nome'
    r = cli.put('/skills/minha', json={'nome': 'minha', 'descricao': 'Outra.', 'instrucoes': 'Z.', 'para': ['codex']})
    assert r.json()['para'] == ['codex']
    assert cli.put('/skills/docx/ligada', json={'ligada': False}).json() == {'ok': True}
    assert banco.ajuste('skills_desligadas') == ['docx']
    assert cli.put('/skills/nada/ligada', json={'ligada': False}).status_code == 404
    nomes = [s['nome'] for s in cli.get('/skills').json()['skills']]
    assert nomes == ['minha', 'plano-de-aula-wit', 'docx']
    assert cli.delete('/skills/minha').json() == {'ok': True}
    assert cli.delete('/skills/minha').status_code == 404
