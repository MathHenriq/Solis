"""Importação do ChatGPT e do Claude, com exportações de amostra.

A do ChatGPT reproduz as armadilhas conhecidas do formato: a conversa é uma
árvore (aqui com uma resposta regenerada num galho abandonado), o nó de sistema
vem vazio, e uma das partes é imagem, não texto."""
import asyncio
import json
import zipfile

import pytest

from solis import banco, importar, ollama

CHATGPT = [{
    'id': 'conv-1',
    'title': 'Sistema de NF-e',
    'create_time': 1678800000.0,  # 14/03/2023
    'current_node': 'n4',
    'mapping': {
        'raiz': {'id': 'raiz', 'message': None, 'parent': None, 'children': ['n1']},
        'n1': {'id': 'n1', 'parent': 'raiz', 'children': ['n2'], 'message': {
            'author': {'role': 'system'}, 'create_time': None, 'content': {'content_type': 'text', 'parts': ['']}}},
        'n2': {'id': 'n2', 'parent': 'n1', 'children': ['n3', 'n3b'], 'message': {
            'author': {'role': 'user'}, 'create_time': 1678800001.0,
            'content': {'content_type': 'multimodal_text', 'parts': [{'asset_pointer': 'img'}, 'como faço a nfe da loja?']}}},
        'n3b': {'id': 'n3b', 'parent': 'n2', 'children': [], 'message': {
            'author': {'role': 'assistant'}, 'create_time': 1678800002.0,
            'content': {'content_type': 'text', 'parts': ['resposta regenerada e abandonada']}}},
        'n3': {'id': 'n3', 'parent': 'n2', 'children': ['n4'], 'message': {
            'author': {'role': 'assistant'}, 'create_time': 1678800003.0,
            'content': {'content_type': 'text', 'parts': ['Precisa de certificado A1.']}}},
        'n4': {'id': 'n4', 'parent': 'n3', 'children': [], 'message': {
            'author': {'role': 'user'}, 'create_time': 1678800004.0,
            'content': {'content_type': 'text', 'parts': ['isso é privado: o CNPJ é 12.345']}}},
    },
}]

CLAUDE = [{
    'uuid': 'c-1',
    'name': 'Estudos de pandas',
    'created_at': '2025-06-01T10:00:00.000000Z',
    'chat_messages': [
        {'sender': 'human', 'text': 'estou estudando pandas', 'created_at': '2025-06-01T10:00:01Z'},
        # Variação: texto só nos blocos de conteúdo.
        {'sender': 'assistant', 'text': '', 'created_at': '2025-06-01T10:00:02Z',
         'content': [{'type': 'text', 'text': 'Ótimo, comece por DataFrame.'}]},
    ],
}]


def test_chatgpt_segue_o_fio_que_aparecia_na_tela():
    msgs = importar.mensagens_chatgpt(CHATGPT[0])
    assert [(m['papel'], m['texto']) for m in msgs] == [
        ('pessoa', 'como faço a nfe da loja?'),
        ('solis', 'Precisa de certificado A1.'),
        ('pessoa', 'isso é privado: o CNPJ é 12.345'),
    ]
    assert msgs[0]['criada'] == '2023-03-14T13:20:01+00:00'


def test_chatgpt_com_ciclo_nao_trava():
    ciclo = {'current_node': 'a', 'mapping': {
        'a': {'parent': 'b', 'message': None}, 'b': {'parent': 'a', 'message': None}}}
    assert importar.mensagens_chatgpt(ciclo) == []


def test_claude_aceita_texto_nos_blocos():
    msgs = importar.mensagens_claude(CLAUDE[0])
    assert [m['texto'] for m in msgs] == ['estou estudando pandas', 'Ótimo, comece por DataFrame.']


def test_formato_e_reconhecido_sozinho():
    assert importar.formato(CHATGPT) == 'chatgpt' and importar.formato(CLAUDE) == 'claude'
    with pytest.raises(ValueError):
        importar.formato([{'outra': 'coisa'}])


def test_le_o_zip_da_exportacao(tmp_path):
    zip_ = tmp_path / 'export.zip'
    with zipfile.ZipFile(zip_, 'w') as z:
        z.writestr('conversations.json', json.dumps(CHATGPT))
        z.writestr('user.json', '{}')
    assert importar.ler_arquivo(zip_) == CHATGPT


def test_guarda_com_origem_e_datas_e_nao_duplica():
    r = importar.guardar(CHATGPT, 'chatgpt')
    assert (r['novas'], r['mensagens']) == (1, 3)
    [linha] = banco._con().execute('SELECT id, origem, titulo, criada FROM conversas').fetchall()
    assert (linha['origem'], linha['titulo'], linha['criada'][:10]) == ('chatgpt', 'Sistema de NF-e', '2023-03-14')
    # O sigilo dito ao ChatGPT continua sigilo aqui.
    assert [m['privada'] for m in banco.mensagens(linha['id'])] == [False, False, True]

    assert importar.guardar(CHATGPT, 'chatgpt')['repetidas'] == 1
    assert banco._con().execute('SELECT count(*) FROM conversas').fetchone()[0] == 1


def test_importada_nao_vira_a_conversa_aberta():
    importar.guardar(CLAUDE, 'claude')
    assert banco.ultima_conversa() is None


def test_trecho_importado_diz_quem_falou():
    importar.guardar(CHATGPT, 'chatgpt')
    [m] = banco.mensagens_por_id([2])
    assert ollama.autor(m) == 'ChatGPT'


def test_aprender_importada_usa_a_data_nao_substitui_e_continua_de_onde_parou(monkeypatch):
    banco.adicionar_memoria('Trabalha na Syngenta.', 'Trabalho', False, None)
    [atual] = banco.memorias()
    perguntas = []

    async def extrai(modelo, instrucao, texto, esquema):
        perguntas.append(texto)
        # O modelo tenta substituir a memória de hoje por um fato antigo.
        return {'memorias': [{'texto': 'Em 2023, trabalhava na loja dos pais.', 'tema': 'Trabalho',
                              'privada': False, 'substitui': atual['id']}]}
    monkeypatch.setattr(ollama, 'responder_json', extrai)

    importar.guardar(CHATGPT, 'chatgpt')
    asyncio.run(importar.aprender_importadas('m', aviso=lambda _: None))

    textos = {m['texto'] for m in banco.memorias()}
    assert textos == {'Trabalha na Syngenta.', 'Em 2023, trabalhava na loja dos pais.'}
    assert 'conversa antiga (ChatGPT, 2023-03-14)' in perguntas[0]
    # Só as falas do Matheus, não as respostas do ChatGPT.
    assert 'certificado A1' not in perguntas[0]
    # Rodar de novo não refaz o que já foi aprendido.
    asyncio.run(importar.aprender_importadas('m', aviso=lambda _: None))
    assert len(perguntas) == 1


def test_linha_de_comando(tmp_path, capsys):
    arquivo = tmp_path / 'conversations.json'
    arquivo.write_text(json.dumps(CLAUDE), encoding='utf-8')
    importar.main([str(arquivo)])
    saida = capsys.readouterr().out
    assert 'claude: 1 conversas novas (2 mensagens)' in saida
    assert 'Faltou parte' in saida  # sem Ollama nos testes, a vetorização fica pra depois
