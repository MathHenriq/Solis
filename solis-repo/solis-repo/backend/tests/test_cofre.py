"""O cofre: o que é privado fica criptografado no banco e volta legível pro Solis.

Os testes olham o que está GRAVADO (a coluna crua), não só o que as funções
devolvem — devolver certo é fácil; o ponto é não estar legível no arquivo."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from solis import banco, cofre, main

com_dpapi = pytest.mark.skipif(not cofre.DISPONIVEL, reason='DPAPI só existe no Windows')


def cru(sql: str, *args):
    return banco._con().execute(sql, args).fetchone()[0]


@com_dpapi
def test_selar_e_abrir():
    selado = cofre.selar('Tem asma desde criança.')
    assert selado.startswith(cofre.PREFIXO) and 'asma' not in selado
    assert cofre.abrir(selado) == 'Tem asma desde criança.'
    assert cofre.selar(selado) == selado            # selar de novo não faz nada
    assert cofre.abrir('texto de antes') == 'texto de antes'
    assert cofre.abrir(cofre.PREFIXO + 'QUJD') == cofre.ILEGIVEL  # não abre: não derruba


@com_dpapi
def test_memoria_privada_fica_selada_e_fora_do_indice():
    privada = banco.adicionar_memoria('Tem asma desde criança.', 'Saúde', False, None, privada=True)
    publica = banco.adicionar_memoria('Mora em Campinas.', 'Moradia', False, None)
    assert cru('SELECT texto FROM memorias WHERE id = ?', privada).startswith(cofre.PREFIXO)
    assert cru('SELECT texto FROM memorias WHERE id = ?', publica) == 'Mora em Campinas.'
    # O índice de busca não tem o texto da privada.
    assert cru('SELECT COUNT(*) FROM memorias_fts WHERE rowid = ?', privada) == 0
    # Mas ela volta legível, e a busca a acha (sem acento e por prefixo).
    assert {m['id']: m['texto'] for m in banco.memorias()}[privada] == 'Tem asma desde criança.'
    assert [m['id'] for m in banco.buscar_memorias('crianca')] == [privada]
    assert [m['id'] for m in banco.buscar_memorias('campi')] == [publica]


@com_dpapi
def test_conversa_com_segredo_sela_mensagem_resposta_titulo_resumo_e_etapas():
    cid = banco.nova_conversa()
    banco.guardar_titulo(cid, 'Senha do wifi')
    pergunta = banco.adicionar(cid, 'pessoa', 'a senha do wifi é solis2026')
    resposta = banco.adicionar(cid, 'solis', 'Anotei: solis2026.')
    banco.guardar_etapas(resposta, [{'etapa': 'aprendizado', 't': 1.0, 'textos': ['Senha do wifi: solis2026']}])
    banco.guardar_resumo(cid, '- a senha é solis2026', 0)
    # Até aqui nada era privado. O aprendizado descobre o sigilo e marca:
    banco.marcar_privada(pergunta)

    linha = banco._con().execute('SELECT titulo, resumo FROM conversas WHERE id = ?', (cid,)).fetchone()
    gravado = [
        cru('SELECT texto FROM mensagens WHERE id = ?', pergunta),
        cru('SELECT texto FROM mensagens WHERE id = ?', resposta),
        cru('SELECT etapas FROM mensagens WHERE id = ?', resposta),
        linha['titulo'],
        linha['resumo'],
    ]
    assert all(v.startswith(cofre.PREFIXO) for v in gravado)
    assert not any('solis2026' in v for v in gravado)
    # E tudo volta legível pra quem usa.
    assert [m['texto'] for m in banco.mensagens(cid)] == ['a senha do wifi é solis2026', 'Anotei: solis2026.']
    assert banco.mensagens(cid)[1]['etapas'][0]['textos'] == ['Senha do wifi: solis2026']
    assert banco.titulo(cid) == 'Senha do wifi' and banco.resumo(cid)[0] == '- a senha é solis2026'
    assert banco.conversas()[0]['titulo'] == 'Senha do wifi'
    # O que chega depois numa conversa com segredo já é gravado selado.
    banco.guardar_titulo(cid, 'Wi-fi de casa')
    assert cru('SELECT titulo FROM conversas WHERE id = ?', cid).startswith(cofre.PREFIXO)


@com_dpapi
def test_mensagem_dita_em_sigilo_ja_entra_selada():
    cid = banco.nova_conversa()
    mid = banco.adicionar(cid, 'pessoa', 'isso é privado: tenho asma', privada=True)
    assert cru('SELECT texto FROM mensagens WHERE id = ?', mid).startswith(cofre.PREFIXO)
    # Pros vetores e pros trechos antigos, o texto volta aberto.
    assert banco.sem_vetor('mensagem', 10)[0]['texto'] == 'isso é privado: tenho asma'
    assert banco.mensagens_por_id([mid])[0]['texto'] == 'isso é privado: tenho asma'


@com_dpapi
def test_o_que_era_privado_antes_do_cofre_e_selado_ao_abrir_o_banco(tmp_path):
    caminho = tmp_path / 'antes.db'
    with sqlite3.connect(caminho) as c:
        c.executescript(banco.ESQUEMA)
        for sql in banco.MIGRACOES[:5]:
            c.executescript(sql)
        c.execute("INSERT INTO conversas (id, criada, titulo) VALUES (1, '2026-11-01', 'Asma')")
        c.execute("INSERT INTO mensagens (conversa, papel, texto, criada, privada) "
                  "VALUES (1, 'pessoa', 'tenho asma', '2026-11-01', 1)")
        c.execute("INSERT INTO memorias (texto, tema, criada, privada) VALUES ('Tem asma.', 'Saúde', '2026-11-01', 1)")
        c.execute("INSERT INTO memorias (texto, tema, criada) VALUES ('Mora em Campinas.', 'Moradia', '2026-11-01')")
        c.execute('PRAGMA user_version = 5')
    banco.usar(caminho)
    assert cru("SELECT texto FROM memorias WHERE tema = 'Saúde'").startswith(cofre.PREFIXO)
    assert cru('SELECT texto FROM mensagens WHERE id = 1').startswith(cofre.PREFIXO)
    assert cru('SELECT titulo FROM conversas WHERE id = 1').startswith(cofre.PREFIXO)
    # A migração 6 refez o índice só com as públicas.
    assert cru('SELECT COUNT(*) FROM memorias_fts') == 1
    assert {m['texto'] for m in banco.memorias()} == {'Tem asma.', 'Mora em Campinas.'}
    # Abrir de novo não sela duas vezes.
    selado = cru("SELECT texto FROM memorias WHERE tema = 'Saúde'")
    banco.usar(caminho)
    assert cru("SELECT texto FROM memorias WHERE tema = 'Saúde'") == selado


@com_dpapi
def test_rota_de_memorias_devolve_a_privada_legivel():
    banco.adicionar_memoria('Tem asma.', 'Saúde', False, None, privada=True)
    [m] = TestClient(main.app).get('/memorias').json()['memorias']
    assert (m['texto'], m['privada']) == ('Tem asma.', True)


def test_sem_dpapi_fica_como_esta_e_o_selado_nao_derruba(monkeypatch):
    monkeypatch.setattr(cofre, 'DISPONIVEL', False)
    assert cofre.selar('Tem asma.') == 'Tem asma.'
    assert cofre.abrir(cofre.PREFIXO + 'QUJD') == cofre.ILEGIVEL
    mid = banco.adicionar_memoria('Tem asma.', 'Saúde', False, None, privada=True)
    assert cru('SELECT texto FROM memorias WHERE id = ?', mid) == 'Tem asma.'


@com_dpapi
def test_o_segredo_descoberto_depois_nao_sobra_no_arquivo(tmp_path):
    """Sem a palavra "privado", o sigilo só aparece no aprendizado — a mensagem
    e o título já foram gravados legíveis. Depois de selar, o texto antigo não
    pode sobrar nem no espaço livre das páginas nem no -wal."""
    caminho = tmp_path / 'solis.db'
    banco.usar(caminho)
    cid = banco.nova_conversa()
    mid = banco.adicionar(cid, 'pessoa', 'a senha do banco é XQZ7731')
    banco.adicionar(cid, 'solis', 'Anotado: XQZ7731.')
    banco.guardar_titulo(cid, 'Senha XQZ7731')
    banco.marcar_privada(mid)
    for arquivo in (caminho, caminho.with_name('solis.db-wal')):
        if arquivo.exists():
            assert b'XQZ7731' not in arquivo.read_bytes(), arquivo.name
    assert banco.mensagens(cid)[0]['texto'] == 'a senha do banco é XQZ7731'
