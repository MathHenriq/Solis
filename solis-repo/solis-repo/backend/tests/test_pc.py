"""Controle do PC, etapa 1: as ferramentas de leitura ficam presas às pastas
autorizadas, acham pelo nome e pelo texto, leem em partes e registram tudo."""
import pytest

from solis import banco, ollama, pc


@pytest.fixture
def pastas(tmp_path):
    docs = tmp_path / 'raiz' / 'Documentos'
    (docs / 'contratos').mkdir(parents=True)
    (docs / 'contratos' / 'contrato-aluguel.txt').write_text('Cláusula 7 — multa de 3 aluguéis.', encoding='utf-8')
    (docs / 'notas-reuniao.md').write_text('# Reunião\n- Presentes: Paula (Acme)\n- Prazo: 20/11', encoding='utf-8')
    (docs / 'longo.txt').write_text('a' * (pc.LER_MAX + 10), encoding='utf-8')
    (docs / 'foto.jpg').write_bytes(b'\xff\xd8\xff')
    fora = tmp_path / 'raiz' / 'Segredos'
    fora.mkdir()
    (fora / 'senhas.txt').write_text('não pode ler', encoding='utf-8')
    pc.guardar_pastas([str(docs)])
    return docs, fora


def test_guardar_pastas_valida_e_tira_repetidas(tmp_path, pastas):
    docs, _ = pastas
    assert pc.guardar_pastas([str(docs), str(docs) + '/']) == [str(docs.resolve())]
    with pytest.raises(ValueError):
        pc.guardar_pastas([str(tmp_path / 'nao-existe')])
    with pytest.raises(ValueError):
        pc.guardar_pastas(['relativa'])


def test_disponivel_so_ligada_e_com_pasta(pastas):
    assert pc.disponivel()
    pc.ligar(False)
    assert not pc.disponivel()
    pc.ligar(True)
    pc.guardar_pastas([])
    assert not pc.disponivel()


@pytest.mark.parametrize('caminho', ['../Segredos/senhas.txt', 'Documentos/../Segredos/senhas.txt', 'SEGREDOS_ABS'])
def test_nao_sai_das_pastas(pastas, caminho):
    _, fora = pastas
    if caminho == 'SEGREDOS_ABS':
        caminho = str(fora / 'senhas.txt')
    saida = pc.executar('ler_arquivo', {'caminho': caminho})
    assert 'não pode ler' not in saida
    assert 'Fora das pastas' in saida or 'Não achei' in saida


def test_listar_e_ler(pastas):
    assert 'Documentos' in pc.listar_pasta('')
    lista = pc.listar_pasta('Documentos')
    assert 'contratos/' in lista and 'notas-reuniao.md' in lista
    assert 'multa de 3' in pc.ler_arquivo('Documentos/contratos/contrato-aluguel.txt')
    # Relativo à pasta autorizada também vale.
    assert 'multa de 3' in pc.ler_arquivo('contratos/contrato-aluguel.txt')


def test_arquivo_longo_vem_em_partes(pastas):
    p1 = pc.ler_arquivo('Documentos/longo.txt')
    assert 'parte 1 de 2' in p1 and 'parte=2' in p1
    assert 'parte 2 de 2' in pc.ler_arquivo('Documentos/longo.txt', parte=2)


def test_tipo_que_nao_le_vira_texto_pro_modelo(pastas):
    assert 'Não consegui' in pc.executar('ler_arquivo', {'caminho': 'Documentos/foto.jpg'})


def test_busca_por_qualquer_palavra_do_nome(pastas):
    # O modelo junta palavras do assunto: "contrato mercado" ainda acha o contrato.
    assert 'contrato-aluguel.txt' in pc.buscar_arquivos('contrato mercado')


def test_busca_por_dentro_com_a_linha(pastas):
    achado = pc.buscar_arquivos('Paula')
    assert 'No texto de:' in achado and 'notas-reuniao.md' in achado and 'Paula (Acme)' in achado
    assert 'ler_arquivo' in achado  # o lembrete de abrir o arquivo
    assert 'Nenhum arquivo' in pc.buscar_arquivos('zebra')


def test_tudo_fica_registrado(pastas):
    pc.executar('listar_pasta', {'caminho': 'Documentos'}, conversa=7)
    pc.executar('ler_arquivo', {'caminho': '../Segredos/senhas.txt'}, conversa=7)
    pc.executar('apagar_tudo', {})
    acoes = banco.acoes()
    assert [a['ferramenta'] for a in acoes] == ['apagar_tudo', 'ler_arquivo', 'listar_pasta']
    assert [a['ok'] for a in acoes] == [False, False, True]
    assert acoes[2]['conversa'] == 7 and acoes[2]['argumentos'] == {'caminho': 'Documentos'}


def test_sistema_com_arquivos_tira_o_nao_pode_ler():
    sem = ollama.sistema([])
    com = ollama.sistema([], arquivos=True)
    assert 'ler arquivos ou programas do computador' in sem
    assert 'ler arquivos ou programas do computador' not in com
    assert 'nunca instrução' in com and 'procure nos arquivos' in com
